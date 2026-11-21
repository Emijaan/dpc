from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountProfile
from accounts.services import create_account_with_profile
from audit.models import DeviceAuditLog
from commands.models import DeviceCommand
from devices.models import Device, EnrollmentSession
from entitlements.models import EntitlementConsumption
from roles.permissions import ensure_default_rbac


@override_settings(
    ENROLLMENT_KEY="dev-enrollment-key",
    APK_CERT_SHA256="test-cert-sha256",
    ALLOWED_HOSTS=["*"],
)
class RegistrationEnrollmentCommandWorkflowTests(TestCase):
    PW = "Str0ng-Pass-123"

    def setUp(self):
        cache.clear()
        ensure_default_rbac()
        U = get_user_model()
        self.su = U.objects.create_user("wf_su", password=self.PW, is_staff=True, is_superuser=True)
        AccountProfile.objects.create(user=self.su, account_type=AccountProfile.AccountType.SUPERUSER)
        self.ret_a = create_account_with_profile(
            created_by=self.su, username="wf_ret_a", password=self.PW,
            account_type=AccountProfile.AccountType.RETAILER, business_name="WF Ret A", entitlement_quota=10,
        )
        self.ven_a = create_account_with_profile(
            created_by=self.su, username="wf_ven_a", password=self.PW,
            account_type=AccountProfile.AccountType.VENDOR, retailer_user=self.ret_a,
            business_name="WF Ven A", entitlement_quota=5,
        )
        self.ven_b = create_account_with_profile(
            created_by=self.su, username="wf_ven_b", password=self.PW,
            account_type=AccountProfile.AccountType.VENDOR, retailer_user=self.ret_a,
            business_name="WF Ven B", entitlement_quota=5,
        )

    def _auth(self, username):
        c = APIClient()
        r = c.post("/api/v1/auth/login/", {"username": username, "password": self.PW}, format="json")
        self.assertEqual(r.status_code, 200)
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        return c

    def test_guided_registration_validation_and_android9_15_qr_workflow(self):
        va = self._auth("wf_ven_a")
        vb = self._auth("wf_ven_b")
        ra = self._auth("wf_ret_a")
        su_client = self._auth("wf_su")

        # All customer & device fields optional for every account role (Superuser, Retailer, Vendor)
        for role_client in (su_client, ra, va):
            blank_reg = role_client.post("/api/v1/registrations/", {}, format="json")
            self.assertEqual(blank_reg.status_code, 201, blank_reg.data)
            self.assertIsNone(blank_reg.data["customer"])
            tok = blank_reg.data["enrollment_token"]
            self.assertEqual(len(tok), 10)
            self.assertTrue(tok.isdigit())
            self.assertEqual(role_client.post(f"/api/v1/enrollment/{blank_reg.data['enrollment_session']['id']}/cancel/").status_code, 200)

        # Reject Android 8 and invalid IMEI Luhn checksum
        bad_v8 = va.post("/api/v1/registrations/", {
            "customer_name": "Test User", "customer_mobile": "+919876543210", "customer_email": "t@example.com",
            "brand": "Vivo", "model": "Y1", "imei": "490154203237518", "android_version": "8.1",
            "enrollment_method": "QR_9_15",
        }, format="json")
        self.assertEqual(bad_v8.status_code, 400)

        bad_imei = va.post("/api/v1/registrations/", {
            "customer_name": "Test User", "customer_mobile": "+919876543210", "customer_email": "t@example.com",
            "brand": "Vivo", "model": "1902", "imei": "490154203237519", "android_version": "9",
            "enrollment_method": "QR_9_15",
        }, format="json")
        self.assertEqual(bad_imei.status_code, 400)

        # Valid registration creates pending device + session without consuming entitlement
        reg = va.post("/api/v1/registrations/", {
            "customer_name": "Asha Devi", "customer_mobile": "+919876543210", "customer_email": "asha@example.com",
            "brand": "Vivo", "model": "1902", "imei": "490154203237518", "android_version": "9",
            "enrollment_method": "QR_9_15",
        }, format="json")
        self.assertEqual(reg.status_code, 201, reg.data)
        sid = reg.data["enrollment_session"]["id"]
        tok = reg.data["enrollment_token"]
        dev_id = reg.data["device"]["id"]
        self.assertEqual(reg.data["device"]["enrollment_status"], "PENDING")
        self.assertEqual(reg.data["device"]["imei_masked"], "***********7518")
        self.assertEqual(va.get("/api/v1/entitlements/balance/").data["available"], 5)

        # Guided QR steps: Test DPC -> mark complete -> AK DeviceLock QR
        step1 = va.get(f"/api/v1/enrollment/{sid}/qr/?step=testdpc&format=json")
        self.assertEqual(step1.status_code, 200)
        self.assertEqual(va.post(f"/api/v1/enrollment/{sid}/complete/", {"step": "test_dpc"}, format="json").status_code, 200)
        step2 = va.get(f"/api/v1/enrollment/{sid}/qr/?step=akdl&format=json")
        self.assertEqual(step2.status_code, 200)
        self.assertEqual(va.get("/api/v1/entitlements/balance/").data["available"], 5)

        # Cross-vendor cannot read status, QR, or cancel
        self.assertEqual(vb.get(f"/api/v1/enrollment/{sid}/status/").status_code, 403)
        self.assertEqual(vb.get(f"/api/v1/enrollment/{sid}/qr/").status_code, 403)
        self.assertEqual(vb.post(f"/api/v1/enrollment/{sid}/cancel/").status_code, 403)

        # Device completes enrollment -> updates pending device in place & consumes 1 entitlement
        dev_reg = APIClient().post(
            "/api/v1/devices/register/",
            {"device_identifier": "vivo-1902-real-01", "sdk_version": 28, "app_version": "0.9.0"},
            format="json",
            HTTP_X_ENROLLMENT_TOKEN=tok,
        )
        self.assertEqual(dev_reg.status_code, 201, dev_reg.data)
        self.assertEqual(dev_reg.data["device_id"], dev_id)
        dev = Device.objects.get(pk=dev_id)
        self.assertEqual(dev.enrollment_status, Device.Enrollment.ENROLLED)
        self.assertEqual(va.get("/api/v1/entitlements/balance/").data["available"], 4)
        self.assertEqual(EntitlementConsumption.objects.filter(device=dev).count(), 1)

        # Superuser filters by IMEI/brand/android_version & audited PII reveal
        su = self._auth("wf_su")
        self.assertEqual(su.get("/api/v1/devices/?q=490154203237518").data["count"], 1)
        self.assertEqual(su.get("/api/v1/devices/?brand=Vivo&android_version=9").data["count"], 1)
        rev = va.get(f"/api/v1/devices/{dev_id}/reveal-imei/")
        self.assertEqual(rev.status_code, 200)
        self.assertEqual(rev.data["imei"], "490154203237518")
        self.assertEqual(vb.get(f"/api/v1/devices/{dev_id}/reveal-imei/").status_code, 403)
        self.assertTrue(DeviceAuditLog.objects.filter(event="PII_REVEALED", device=dev).exists())

    def test_28_to_30_android16_bat_expiry_reuse_and_cancel(self):
        va = self._auth("wf_ven_a")
        vb = self._auth("wf_ven_b")

        reg = va.post("/api/v1/registrations/", {
            "customer_name": "Sam User", "customer_mobile": "+919111222333", "customer_email": "sam@example.com",
            "brand": "Samsung", "model": "SM-X115", "imei": "490154203237518", "android_version": "16",
            "enrollment_method": "ADB_16",
        }, format="json")
        self.assertEqual(reg.status_code, 201)
        sid = reg.data["enrollment_session"]["id"]

        # BAT file contains safety checks and session token, never static ENROLLMENT_KEY
        bat = va.get(f"/api/v1/enrollment/{sid}/bat/")
        self.assertEqual(bat.status_code, 200)
        body = bat.content.decode()
        self.assertIn("where adb", body)
        self.assertIn("adb get-state", body)
        self.assertIn("dpm list-owners", body)
        self.assertIn("dpm set-device-owner", body)
        self.assertNotIn("dev-enrollment-key", body)
        self.assertEqual(vb.get(f"/api/v1/enrollment/{sid}/bat/").status_code, 403)

        # 28. Expired enrollment session cannot register
        EnrollmentSession.objects.filter(pk=sid).update(expires_at=timezone.now() - timedelta(minutes=1))
        st = va.get(f"/api/v1/enrollment/{sid}/status/").data
        self.assertEqual(st["status"], "EXPIRED")
        self.assertFalse(st["entitlement_consumed"])
        self.assertEqual(
            APIClient().post(
                "/api/v1/devices/register/",
                {"device_identifier": "sam-exp-01"},
                format="json",
                HTTP_X_ENROLLMENT_TOKEN=reg.data["enrollment_token"],
            ).status_code,
            403,
        )
        # Cancel an unused session preserves entitlement
        reg2 = va.post("/api/v1/registrations/", {
            "customer_name": "Cancel User", "customer_mobile": "+919111222444", "customer_email": "can@example.com",
            "brand": "Samsung", "model": "A15", "imei": "490154203237518", "android_version": "14",
        }, format="json")
        sid2 = reg2.data["enrollment_session"]["id"]
        self.assertEqual(va.post(f"/api/v1/enrollment/{sid2}/cancel/").status_code, 200)
        self.assertEqual(va.get("/api/v1/entitlements/balance/").data["available"], 5)

        # Used & released enrollment key cannot be reused or re-downloaded
        fresh_reg = va.post("/api/v1/registrations/", {
            "brand": "Samsung", "model": "SM-X115", "android_version": "16",
            "enrollment_method": "ADB_16",
        }, format="json")
        self.assertEqual(fresh_reg.status_code, 201)
        fsid = fresh_reg.data["enrollment_session"]["id"]
        ftok = fresh_reg.data["enrollment_token"]
        r1 = APIClient().post(
            "/api/v1/devices/register/",
            {"device_identifier": "sm-x115-rel-1"},
            HTTP_X_ENROLLMENT_TOKEN=ftok,
            format="json",
        )
        self.assertEqual(r1.status_code, 201)
        dev_id = r1.data["device_id"]
        dev_tok = r1.data["device_token"]
        rel = va.post(f"/api/v1/devices/{dev_id}/release/", {}, format="json")
        self.assertIn(rel.status_code, (200, 201))
        cmd_id = rel.data["command_id"]
        dev_client = APIClient()
        dev_client.credentials(HTTP_AUTHORIZATION="Device " + dev_tok)
        self.assertEqual(dev_client.post("/api/v1/commands/acknowledge/", {"command_id": cmd_id, "success": True, "result": "released"}, format="json").status_code, 200)
        # Reusing the same token after release must be rejected, and .bat download must be 409
        r2 = APIClient().post(
            "/api/v1/devices/register/",
            {"device_identifier": "sm-x115-rel-2"},
            HTTP_X_ENROLLMENT_TOKEN=ftok,
            format="json",
        )
        self.assertEqual(r2.status_code, 403)
        self.assertEqual(va.get(f"/api/v1/enrollment/{fsid}/bat/").status_code, 409)

    def test_31_to_36_offline_pending_states_ack_and_append_only_audit(self):
        va = self._auth("wf_ven_a")
        vb = self._auth("wf_ven_b")
        er = va.post("/api/v1/enrollments/", {"customer_name": "Cmd Cust"}, format="json").data
        reg = APIClient().post(
            "/api/v1/devices/register/",
            {"device_identifier": "cmd-dev-0001"},
            format="json",
            HTTP_X_ENROLLMENT_TOKEN=er["enrollment_token"],
        ).data
        dev_id = reg["device_id"]
        dc = APIClient()
        dc.credentials(HTTP_AUTHORIZATION="Device " + reg["device_token"])

        # 31. Unauthorized command creation blocked
        self.assertEqual(vb.post(f"/api/v1/devices/{dev_id}/lock/").status_code, 403)

        # 35. Offline device marked LOCK_PENDING, NOT falsely marked LOCKED; sync does not clobber LOCK_PENDING
        Device.objects.filter(pk=dev_id).update(last_seen=timezone.now() - timedelta(hours=2))
        lock_r = va.post(f"/api/v1/devices/{dev_id}/lock/")
        self.assertEqual(lock_r.status_code, 201)
        self.assertFalse(lock_r.data["device_online"])
        self.assertEqual(Device.objects.get(pk=dev_id).restriction_status, Device.Restriction.LOCK_PENDING)
        dc.post("/api/v1/devices/sync/", {"restriction_status": "NONE"}, format="json")
        self.assertEqual(Device.objects.get(pk=dev_id).restriction_status, Device.Restriction.LOCK_PENDING)

        # Background tasks execute cleanly
        from commands.tasks import expire_stale_commands_task
        from entitlements.tasks import expire_stale_allocations_task
        self.assertEqual(expire_stale_commands_task(), 1)
        self.assertIsInstance(expire_stale_allocations_task(), int)

        # 32. Expired command rejected
        DeviceCommand.objects.filter(pk=lock_r.data["command_id"]).update(
            expires_at=timezone.now() - timedelta(seconds=10)
        )
        self.assertEqual(dc.get("/api/v1/commands/pending/").data["commands"], [])

        # 34. Fresh lock -> ack updates actual status to LOCKED; unlock -> UNLOCK_PENDING -> ack -> NONE
        lock2 = va.post(f"/api/v1/devices/{dev_id}/lock/")
        self.assertEqual(lock2.status_code, 201)
        dc.get("/api/v1/commands/pending/")
        dc.post("/api/v1/commands/acknowledge/", {"command_id": lock2.data["command_id"], "success": True}, format="json")
        self.assertEqual(Device.objects.get(pk=dev_id).restriction_status, Device.Restriction.LOCKED)

        # 33. Replay ack is idempotent and does not change state
        rep = dc.post("/api/v1/commands/acknowledge/", {"command_id": lock2.data["command_id"], "success": False}, format="json")
        self.assertTrue(rep.data["duplicate"])
        self.assertEqual(Device.objects.get(pk=dev_id).restriction_status, Device.Restriction.LOCKED)

        # Audit logs are append-only
        log_row = DeviceAuditLog.objects.first()
        with self.assertRaises(ValidationError):
            log_row.delete()

        # Dashboard stats work for all 3 levels
        self.assertEqual(self._auth("wf_su").get("/api/v1/dashboard/stats/").status_code, 200)
        self.assertEqual(self._auth("wf_ret_a").get("/api/v1/dashboard/stats/").status_code, 200)
        self.assertEqual(va.get("/api/v1/dashboard/stats/").status_code, 200)

        # GPS, Camera, and Network telemetry + policy endpoints
        sync_tel = dc.post("/api/v1/devices/sync/", {
            "latitude": 28.6139, "longitude": 77.2090, "location_accuracy": 12.5,
            "network_type": "WIFI", "wifi_ssid": "OfficeNet", "network_operator": "Jio", "ip_address": "192.168.1.50",
        }, format="json")
        self.assertEqual(sync_tel.status_code, 200)
        dev_obj = va.get(f"/api/v1/devices/{dev_id}/").data
        self.assertAlmostEqual(dev_obj["last_latitude"], 28.6139, places=4)
        self.assertEqual(dev_obj["network_type"], "WIFI")
        self.assertEqual(dev_obj["wifi_ssid"], "OfficeNet")

        import base64
        sample_b64 = base64.b64encode(b"\xff\xd8\xff\xe0test-jpeg").decode()
        self.assertEqual(dc.post("/api/v1/devices/photo/", {"photo_b64": sample_b64}, format="json").status_code, 200)
        self.assertEqual(vb.get(f"/api/v1/devices/{dev_id}/photo/").status_code, 403)
        photo_resp = va.get(f"/api/v1/devices/{dev_id}/photo/")
        self.assertEqual(photo_resp.status_code, 200)
        self.assertEqual(photo_resp.data["photo_b64"], sample_b64)

        self.assertEqual(vb.post(f"/api/v1/devices/{dev_id}/locate/").status_code, 403)
        self.assertEqual(va.post(f"/api/v1/devices/{dev_id}/locate/").status_code, 201)
        self.assertEqual(va.post(f"/api/v1/devices/{dev_id}/capture-photo/").status_code, 201)
        cam_off = va.post(f"/api/v1/devices/{dev_id}/camera/", {"disable": True}, format="json")
        gps_on = va.post(f"/api/v1/devices/{dev_id}/gps-policy/", {"lock": True}, format="json")
        net_lock = va.post(f"/api/v1/devices/{dev_id}/network-policy/", {"restrict": True}, format="json")
        self.assertEqual(cam_off.status_code, 201)
        self.assertEqual(gps_on.status_code, 201)
        self.assertEqual(net_lock.status_code, 201)
        for cid in (cam_off.data["command_id"], gps_on.data["command_id"], net_lock.data["command_id"]):
            self.assertEqual(dc.post("/api/v1/commands/acknowledge/", {"command_id": cid, "success": True}, format="json").status_code, 200)
        dev_after = Device.objects.get(pk=dev_id)
        self.assertTrue(dev_after.camera_disabled)
        self.assertTrue(dev_after.gps_forced_on)
        self.assertTrue(dev_after.network_restricted)

    def test_optional_lock_screen_emi_and_dealer_fields(self):
        # 1. Registration with zero fields works cleanly (every input is optional)
        va = self._auth("wf_ven_a")
        blank_reg = va.post("/api/v1/registrations/", {}, format="json")
        self.assertEqual(blank_reg.status_code, 201, blank_reg.data)
        self.assertEqual(blank_reg.data["device"]["emi_amount"], "")
        self.assertEqual(blank_reg.data["device"]["dealer_company"], "")

        # 2. Registration with partial optional EMI & dealer fields preserves them through enrollment
        partial_reg = va.post(
            "/api/v1/registrations/",
            {
                "emi_amount": "2500",
                "emi_due_date": "2026-12-05",
                "pending_emi_count": "6",
                "dealer_name": "Rahul Sharma",
                "dealer_mobile": "+919876543210",
                "dealer_company": "AK Mobiles",
            },
            format="json",
        )
        self.assertEqual(partial_reg.status_code, 201, partial_reg.data)
        enroll_tok = partial_reg.data["enrollment_token"]

        dc = APIClient()
        dev_reg = dc.post(
            "/api/v1/devices/register/",
            {"device_identifier": "wf-lock-dev-01", "manufacturer": "Vivo", "model": "Y20"},
            HTTP_X_ENROLLMENT_TOKEN=enroll_tok,
            format="json",
        )
        self.assertEqual(dev_reg.status_code, 201, dev_reg.data)
        dev_id = dev_reg.data["device_id"]
        dev_tok = dev_reg.data["device_token"]

        dc.credentials(HTTP_AUTHORIZATION=f"Device {dev_tok}")
        pending_res = dc.get("/api/v1/commands/pending/")
        self.assertEqual(pending_res.status_code, 200)
        self.assertEqual(
            pending_res.data["lock_screen"],
            {
                "emi_amount": "2500",
                "emi_due_date": "2026-12-05",
                "pending_emi_count": "6",
                "dealer_name": "Rahul Sharma",
                "dealer_mobile": "+919876543210",
                "dealer_company": "AK Mobiles",
            },
        )

        # 3. Cross-tenant vendor cannot patch sibling vendor's device
        vb = self._auth("wf_ven_b")
        self.assertEqual(
            vb.patch(f"/api/v1/devices/{dev_id}/", {"emi_amount": "9999"}, format="json").status_code,
            403,
        )

        # 4. Owning vendor can update or blank out any field; sync returns updated lock_screen
        upd = va.patch(
            f"/api/v1/devices/{dev_id}/",
            {"emi_amount": "3000", "dealer_company": ""},
            format="json",
        )
        self.assertEqual(upd.status_code, 200, upd.data)
        self.assertEqual(upd.data["device"]["emi_amount"], "3000")
        self.assertEqual(upd.data["device"]["dealer_company"], "")
        self.assertEqual(upd.data["device"]["dealer_name"], "Rahul Sharma")

        sync_res = dc.post("/api/v1/devices/sync/", {"restriction_status": "NONE"}, format="json")
        self.assertEqual(sync_res.status_code, 200)
        self.assertEqual(sync_res.data["lock_screen"]["emi_amount"], "3000")
        self.assertEqual(sync_res.data["lock_screen"]["dealer_company"], "")
