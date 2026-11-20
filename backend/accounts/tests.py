from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import AccountProfile
from audit.models import DeviceAuditLog
from roles.models import AccountRole, Role
from roles.permissions import ensure_default_rbac


@override_settings(ALLOWED_HOSTS=["*"])
class JwtAuthTests(TestCase):
    PW = "Str0ng-Pass-123"

    def setUp(self):
        cache.clear()
        ensure_default_rbac()
        U = get_user_model()
        self.su = U.objects.create_user("boss", password=self.PW, is_staff=True, is_superuser=True)
        self.ret = U.objects.create_user("ret1", password=self.PW, is_staff=True)
        AccountProfile.objects.create(user=self.ret, account_type=AccountProfile.AccountType.RETAILER)
        AccountRole.objects.create(user=self.ret, role=Role.objects.get(name="RETAILER"))
        self.other = U.objects.create_user("ret2", password=self.PW, is_staff=True)
        AccountProfile.objects.create(user=self.other, account_type=AccountProfile.AccountType.RETAILER)
        self.c = APIClient()

    def login(self, username="ret1", password=None):
        return self.c.post("/api/v1/auth/login/", {"username": username, "password": password or self.PW}, format="json")

    def test_login_returns_tokens_and_profile(self):
        r = self.login()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["access"] and r.data["refresh"])
        self.assertEqual(r.data["user"]["account_type"], "RETAILER")
        self.assertNotIn("password", str(r.data))

    def test_bad_credentials_are_indistinguishable(self):
        wrong = self.login(password="nope-nope-nope")
        unknown = self.login(username="ghost")
        U = get_user_model()
        U.objects.filter(username="ret2").update(is_active=False)
        inactive = self.login(username="ret2")
        for r in (wrong, unknown, inactive):
            self.assertEqual(r.status_code, 401)
            self.assertEqual(r.data, {"error": "invalid_credentials"})

    def test_access_token_authenticates_api_and_me(self):
        access = self.login().data["access"]
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(c.get("/api/v1/auth/me/").data["username"], "ret1")
        self.assertEqual(c.get("/api/v1/devices/").status_code, 200)
        self.assertEqual(APIClient().get("/api/v1/auth/me/").status_code, 401)
        c.credentials(HTTP_AUTHORIZATION="Bearer not.a.token")
        self.assertEqual(c.get("/api/v1/auth/me/").status_code, 401)

    def test_expired_access_token_rejected(self):
        tok = AccessToken.for_user(self.ret)
        tok.set_exp(lifetime=-timedelta(seconds=5))
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")
        self.assertEqual(c.get("/api/v1/auth/me/").status_code, 401)

    def test_refresh_rotates_and_old_token_is_blacklisted(self):
        first = self.login().data["refresh"]
        r = self.c.post("/api/v1/auth/refresh/", {"refresh": first}, format="json")
        self.assertEqual(r.status_code, 200)
        second = r.data["refresh"]
        self.assertNotEqual(first, second)
        # Reusing the rotated (old) refresh token must fail
        reuse = self.c.post("/api/v1/auth/refresh/", {"refresh": first}, format="json")
        self.assertEqual(reuse.status_code, 401)
        self.assertEqual(reuse.data, {"error": "invalid_refresh_token"})
        # The new one still works
        self.assertEqual(self.c.post("/api/v1/auth/refresh/", {"refresh": second}, format="json").status_code, 200)

    def test_logout_blacklists_refresh(self):
        data = self.login().data
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {data['access']}")
        self.assertEqual(c.post("/api/v1/auth/logout/", {"refresh": data["refresh"]}, format="json").status_code, 204)
        self.assertEqual(self.c.post("/api/v1/auth/refresh/", {"refresh": data["refresh"]}, format="json").status_code, 401)

    def test_cannot_logout_with_another_users_refresh_token(self):
        mine = self.login().data
        theirs = self.login(username="ret2").data
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {mine['access']}")
        self.assertEqual(c.post("/api/v1/auth/logout/", {"refresh": theirs["refresh"]}, format="json").status_code, 403)
        # Their token is still valid
        self.assertEqual(self.c.post("/api/v1/auth/refresh/", {"refresh": theirs["refresh"]}, format="json").status_code, 200)

    def test_deactivated_user_cannot_refresh(self):
        refresh = self.login().data["refresh"]
        get_user_model().objects.filter(username="ret1").update(is_active=False)
        self.assertEqual(self.c.post("/api/v1/auth/refresh/", {"refresh": refresh}, format="json").status_code, 401)

    def test_login_is_rate_limited(self):
        codes = [self.login(password="bad-bad-bad-1").status_code for _ in range(12)]
        self.assertEqual(codes[0], 401)
        self.assertIn(429, codes)

    def test_basic_auth_no_longer_accepted(self):
        import base64
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Basic " + base64.b64encode(f"ret1:{self.PW}".encode()).decode())
        self.assertEqual(c.get("/api/v1/devices/").status_code, 401)

    def test_auth_events_audited_without_secrets(self):
        self.login(password="wrong-wrong-1")
        data = self.login().data
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {data['access']}")
        c.post("/api/v1/auth/logout/", {"refresh": data["refresh"]}, format="json")
        events = set(DeviceAuditLog.objects.values_list("event", flat=True))
        self.assertTrue({"LOGIN_FAILED", "LOGIN_SUCCESS", "LOGOUT"} <= events)
        blob = " ".join(DeviceAuditLog.objects.values_list("result", flat=True))
        self.assertNotIn("wrong-wrong-1", blob)
        self.assertNotIn(self.PW, blob)
        self.assertNotIn(data["refresh"], blob)

    def test_health(self):
        r = APIClient().get("/api/v1/health/")
        self.assertEqual((r.status_code, r.data), (200, {"status": "ok"}))

    def test_user_ip_and_device_tracked_for_admin_visibility(self):
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
        r = self.c.post(
            "/api/v1/auth/login/",
            {"username": "ret1", "password": self.PW},
            format="json",
            HTTP_X_FORWARDED_FOR="203.0.113.42, 10.0.0.1",
            HTTP_USER_AGENT=ua,
        )
        self.assertEqual(r.status_code, 200)
        prof = AccountProfile.objects.get(user=self.ret)
        self.assertEqual(prof.last_ip, "203.0.113.42")
        self.assertEqual(prof.last_device, "Chrome on macOS")
        self.assertIn("Chrome/125", prof.last_user_agent)
        self.assertIsNotNone(prof.last_active_at)

        # Authenticated JWT call updates IP/device when client changes
        iphone_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        self.assertEqual(
            c.get("/api/v1/auth/me/", HTTP_X_FORWARDED_FOR="198.51.100.77", HTTP_USER_AGENT=iphone_ua).status_code,
            200,
        )
        prof.refresh_from_db()
        self.assertEqual(prof.last_ip, "198.51.100.77")
        self.assertEqual(prof.last_device, "Safari on iPhone")

        # Superuser sees user IP & device in /api/v1/accounts/ and /api/v1/audit/
        su_login = self.c.post("/api/v1/auth/login/", {"username": "boss", "password": self.PW}, format="json")
        sc = APIClient()
        sc.credentials(HTTP_AUTHORIZATION=f"Bearer {su_login.data['access']}")
        accts = sc.get("/api/v1/accounts/").data["accounts"]
        ret_row = next(a for a in accts if a["username"] == "ret1")
        self.assertEqual(ret_row["last_ip"], "198.51.100.77")
        self.assertEqual(ret_row["last_device"], "Safari on iPhone")

        audits = sc.get("/api/v1/audit/").data["audit_logs"]
        login_log = next(a for a in audits if a["event"] == "LOGIN_SUCCESS" and a["actor"] == "ret1")
        self.assertEqual(login_log["source_ip"], "203.0.113.42")
        self.assertEqual(login_log["client_device"], "Chrome on macOS")
