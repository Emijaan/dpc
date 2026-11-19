from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountProfile
from audit.models import DeviceAuditLog
from commands.models import DeviceCommand
from commands.services import expire_stale
from devices.models import Customer, Device, DeviceOwnershipTransfer, EnrollmentSession
from roles.models import AccountRole, Role
from roles.permissions import ensure_default_rbac


@override_settings(
    ENROLLMENT_KEY="dev-enrollment-key",
    APK_CERT_SHA256="test-cert-sha256",
    ALLOWED_HOSTS=["*"],
)
class TenantOwnershipIsolationTests(TestCase):
    def setUp(self):
        cache.clear()
        ensure_default_rbac()
        U = get_user_model()
        self.su = U.objects.create_user("superuser", password="StrongPass!123", is_staff=True, is_superuser=True)
        AccountProfile.objects.create(user=self.su, account_type=AccountProfile.AccountType.SUPERUSER)

        self.ret_a = U.objects.create_user("retailer_a", password="StrongPass!123", is_staff=True)
        AccountProfile.objects.create(user=self.ret_a, account_type=AccountProfile.AccountType.RETAILER)
        AccountRole.objects.create(user=self.ret_a, role=Role.objects.get(name="RETAILER"))

        self.ret_b = U.objects.create_user("retailer_b", password="StrongPass!123", is_staff=True)
        AccountProfile.objects.create(user=self.ret_b, account_type=AccountProfile.AccountType.RETAILER)
        AccountRole.objects.create(user=self.ret_b, role=Role.objects.get(name="RETAILER"))

        self.ven_a1 = U.objects.create_user("vendor_a1", password="StrongPass!123", is_staff=True)
        AccountProfile.objects.create(
            user=self.ven_a1,
            account_type=AccountProfile.AccountType.VENDOR,
            retailer=self.ret_a,
            entitlement_quota=10,
        )
        AccountRole.objects.create(user=self.ven_a1, role=Role.objects.get(name="VENDOR"))

        self.ven_a2 = U.objects.create_user("vendor_a2", password="StrongPass!123", is_staff=True)
        AccountProfile.objects.create(
            user=self.ven_a2, account_type=AccountProfile.AccountType.VENDOR, retailer=self.ret_a
        )
        AccountRole.objects.create(user=self.ven_a2, role=Role.objects.get(name="VENDOR"))

        self.ven_b1 = U.objects.create_user("vendor_b1", password="StrongPass!123", is_staff=True)
        AccountProfile.objects.create(
            user=self.ven_b1, account_type=AccountProfile.AccountType.VENDOR, retailer=self.ret_b
        )
        AccountRole.objects.create(user=self.ven_b1, role=Role.objects.get(name="VENDOR"))

        # Enroll devices for Vendor A1, Vendor A2, Vendor B1, and Retailer A directly
        self.dev_a1, self.cust_a1, self.sess_a1 = self._enroll_as(
            self.ven_a1, "dev-a1-0001", "Alice A1", "+919876543210", "alice@example.com", "356938035643809"
        )
        self.dev_a2, self.cust_a2, self.sess_a2 = self._enroll_as(
            self.ven_a2, "dev-a2-0003", "Bob A2", "+919111111111", "bob@example.com", "356938035643817"
        )
        self.dev_b1, self.cust_b1, self.sess_b1 = self._enroll_as(
            self.ven_b1, "dev-b1-0005", "Charlie B1", "+919222222222", "charlie@example.com", "356938035643825"
        )
        self.dev_ra, self.cust_ra, self.sess_ra = self._enroll_as(
            self.ret_a, "dev-ra-0007", "Direct RA", "+919333333333", "ra@example.com", "356938035643833"
        )

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def _enroll_as(self, user, ident, cust_name, mobile, email, imei):
        c = self._client(user)
        er = c.post(
            "/api/v1/enrollments/",
            {
                "customer_name": cust_name,
                "customer_mobile": mobile,
                "customer_email": email,
                "intended_device_identifier": ident,
            },
            format="json",
        )
        self.assertEqual(er.status_code, 201, er.data)
        token = er.data["enrollment_token"]
        sess = EnrollmentSession.objects.get(pk=er.data["id"])
        rr = APIClient().post(
            "/api/v1/devices/register/",
            {
                "device_identifier": ident,
                "imei": imei,
                "manufacturer": "Samsung",
                "model": "A15",
                "android_version": "14",
                "sdk_version": 34,
                "app_version": "0.9",
            },
            format="json",
            HTTP_X_ENROLLMENT_TOKEN=token,
        )
        self.assertEqual(rr.status_code, 201, rr.data)
        dev = Device.objects.get(pk=rr.data["device_id"])
        return dev, dev.customer, sess

    def test_1_and_2_vendor_own_and_cross_vendor_access(self):
        va1 = self._client(self.ven_a1)
        # 1. Vendor A1 can access its own device
        r = va1.get(f"/api/v1/devices/{self.dev_a1.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["imei_masked"], "***********3809")
        self.assertNotIn("356938035643809", str(r.data))

        # 2 & 12. Vendor A1 cannot access Vendor A2's or Vendor B1's device (even with UUID manipulation)
        self.assertEqual(va1.get(f"/api/v1/devices/{self.dev_a2.id}/").status_code, 403)
        self.assertEqual(va1.get(f"/api/v1/devices/{self.dev_b1.id}/").status_code, 403)
        self.assertEqual(va1.get(f"/api/v1/devices/{self.dev_ra.id}/").status_code, 403)

        # List, search, and export are strictly scoped to Vendor A1
        listed = [d["id"] for d in va1.get("/api/v1/devices/").data["devices"]]
        self.assertEqual(listed, [str(self.dev_a1.id)])
        searched = va1.get("/api/v1/devices/?q=Charlie").data["devices"]
        self.assertEqual(searched, [])
        exported = va1.get("/api/v1/devices/export/?format=json").data["devices"]
        self.assertEqual([d["id"] for d in exported], [str(self.dev_a1.id)])

    def test_3_4_13_14_vendor_cannot_command_or_sync_other_devices(self):
        va1 = self._client(self.ven_a1)
        for target in (self.dev_a2, self.dev_b1):
            for action in ("lock", "unlock", "sync-command", "status-command"):
                self.assertEqual(va1.post(f"/api/v1/devices/{target.id}/{action}/").status_code, 403)
        self.assertEqual(DeviceCommand.objects.count(), 0)

        # Can lock and sync its own device
        self.assertEqual(va1.post(f"/api/v1/devices/{self.dev_a1.id}/lock/").status_code, 201)
        self.assertEqual(va1.post(f"/api/v1/devices/{self.dev_a1.id}/sync-command/").status_code, 201)

    def test_5_customer_data_isolation_and_encryption(self):
        # Raw PII is encrypted at rest
        self.assertNotIn("9876543210", self.cust_a1.mobile_encrypted)
        self.assertNotIn("alice@example.com", self.cust_a1.email_encrypted)
        self.assertNotIn("356938035643809", self.dev_a1.imei_encrypted)

        va1 = self._client(self.ven_a1)
        own = va1.get(f"/api/v1/customers/{self.cust_a1.id}/")
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.data["mobile_masked"], "*********3210")
        self.assertEqual(own.data["email_masked"], "a***@example.com")

        # Cannot access Vendor A2 or Vendor B1 customers
        self.assertEqual(va1.get(f"/api/v1/customers/{self.cust_a2.id}/").status_code, 403)
        self.assertEqual(va1.get(f"/api/v1/customers/{self.cust_b1.id}/").status_code, 403)
        self.assertEqual(va1.get("/api/v1/customers/?q=Charlie").data["customers"], [])

    def test_6_enrollment_and_qr_isolation_and_single_use(self):
        va1 = self._client(self.ven_a1)
        self.assertEqual(va1.get(f"/api/v1/enrollments/{self.sess_a1.id}/").status_code, 200)
        # The setUp session was already consumed -> QR/BAT are no longer retrievable, detail still is
        self.assertEqual(va1.get(f"/api/v1/enrollments/{self.sess_a1.id}/qr/").status_code, 409)
        self.assertEqual(va1.get(f"/api/v1/enrollments/{self.sess_a1.id}/provision-bat/").status_code, 409)
        fresh = va1.post("/api/v1/enrollments/", {"customer_name": "Fresh"}, format="json").data["id"]
        self.assertEqual(va1.get(f"/api/v1/enrollments/{fresh}/qr/").status_code, 200)
        self.assertEqual(va1.get(f"/api/v1/enrollments/{fresh}/provision-bat/").status_code, 200)

        # Cross-vendor access to a PENDING session's QR/BAT is rejected with 403 for another vendor
        vb1 = self._client(self.ven_b1)
        self.assertEqual(vb1.get(f"/api/v1/enrollments/{fresh}/qr/").status_code, 403)
        self.assertEqual(vb1.get(f"/api/v1/enrollments/{fresh}/provision-bat/").status_code, 403)
        self.assertEqual(vb1.get(f"/api/v1/enrollments/{fresh}/").status_code, 403)

        # Cross-vendor access to enrollment session, QR, and BAT is rejected with 403
        for other_sess in (self.sess_a2, self.sess_b1):
            self.assertEqual(va1.get(f"/api/v1/enrollments/{other_sess.id}/").status_code, 403)
            self.assertEqual(va1.get(f"/api/v1/enrollments/{other_sess.id}/qr/").status_code, 403)
            self.assertEqual(va1.get(f"/api/v1/enrollments/{other_sess.id}/provision-bat/").status_code, 403)

        # Single-use enrollment token cannot be reused
        er = va1.post("/api/v1/enrollments/", {"customer_name": "Reuse Test"}, format="json")
        token = er.data["enrollment_token"]
        r1 = APIClient().post(
            "/api/v1/devices/register/", {"device_identifier": "dev-single-01"}, format="json", HTTP_X_ENROLLMENT_TOKEN=token
        )
        self.assertEqual(r1.status_code, 201)
        r2 = APIClient().post(
            "/api/v1/devices/register/", {"device_identifier": "dev-single-02"}, format="json", HTTP_X_ENROLLMENT_TOKEN=token
        )
        self.assertEqual(r2.status_code, 403)

    def test_8_9_10_retailer_hierarchy_and_isolation(self):
        ra = self._client(self.ret_a)
        # 8. Retailer A sees its own direct device + Vendor A1 + Vendor A2 devices
        ra_ids = {d["id"] for d in ra.get("/api/v1/devices/").data["devices"]}
        self.assertEqual(ra_ids, {str(self.dev_a1.id), str(self.dev_a2.id), str(self.dev_ra.id)})

        # 9. Retailer A cannot access Retailer B's devices or customers
        self.assertEqual(ra.get(f"/api/v1/devices/{self.dev_b1.id}/").status_code, 403)
        self.assertEqual(ra.get(f"/api/v1/customers/{self.cust_b1.id}/").status_code, 403)

        # 10. Retailer A cannot modify Retailer B's vendors, but can manage its own
        self.assertEqual(
            ra.post(f"/api/v1/accounts/{self.ven_b1.id}/status/", {"is_active": False}, format="json").status_code,
            403,
        )
        self.assertEqual(
            ra.post(f"/api/v1/accounts/{self.ven_a1.id}/status/", {"is_active": False}, format="json").status_code,
            200,
        )

    def test_11_superuser_platform_wide_access_and_background_expire(self):
        sc = self._client(self.su)
        all_ids = {d["id"] for d in sc.get("/api/v1/devices/").data["devices"]}
        self.assertEqual(
            all_ids, {str(self.dev_a1.id), str(self.dev_a2.id), str(self.dev_b1.id), str(self.dev_ra.id)}
        )
        self.assertEqual(len(sc.get("/api/v1/customers/").data["customers"]), 4)

        # Background expire_stale works cleanly
        cmd = sc.post(f"/api/v1/devices/{self.dev_a1.id}/lock/").data["command_id"]
        DeviceCommand.objects.filter(pk=cmd).update(expires_at=timezone.now() - timedelta(seconds=10))
        expire_stale()
        self.assertEqual(DeviceCommand.objects.get(pk=cmd).command_status, DeviceCommand.Status.EXPIRED)

    def test_7_15_16_17_release_immutability_and_superuser_transfer(self):
        # 7 & 16. Vendor and Retailer cannot transfer device ownership
        va1 = self._client(self.ven_a1)
        ra = self._client(self.ret_a)
        transfer_payload = {
            "to_retailer_id": self.ret_b.id,
            "to_vendor_id": self.ven_b1.id,
            "reason": "unauthorized attempt",
            "confirm": True,
        }
        self.assertEqual(va1.post(f"/api/v1/devices/{self.dev_a1.id}/transfer/", transfer_payload, format="json").status_code, 403)
        self.assertEqual(ra.post(f"/api/v1/devices/{self.dev_a1.id}/transfer/", transfer_payload, format="json").status_code, 403)

        # 16 & 17. Superuser transfer requires confirmation + reason, preserves original_vendor, audits, and never restores quota
        consumed_before = AccountProfile.objects.get(user=self.ven_a1).entitlements_consumed
        self.assertEqual(consumed_before, 1)

        sc = self._client(self.su)
        tr = sc.post(
            f"/api/v1/devices/{self.dev_a1.id}/transfer/",
            {"to_retailer_id": self.ret_b.id, "to_vendor_id": self.ven_b1.id, "reason": "store closure", "confirm": True},
            format="json",
        )
        self.assertEqual(tr.status_code, 200, tr.data)
        self.dev_a1.refresh_from_db()
        self.assertEqual(self.dev_a1.original_vendor_id, self.ven_a1.id)
        self.assertEqual(self.dev_a1.vendor_id, self.ven_b1.id)
        self.assertEqual(self.dev_a1.ownership_status, Device.OwnershipStatus.TRANSFERRED)
        self.assertEqual(DeviceOwnershipTransfer.objects.filter(device=self.dev_a1).count(), 1)
        self.assertTrue(DeviceAuditLog.objects.filter(device=self.dev_a1, event="DEVICE_OWNERSHIP_TRANSFERRED").exists())
        # Entitlements not restored
        self.assertEqual(AccountProfile.objects.get(user=self.ven_a1).entitlements_consumed, 1)

        # 15. Release retains historical ownership and never restores entitlement quota
        rel_cmd = sc.post(f"/api/v1/devices/{self.dev_a2.id}/release/").data["command_id"]
        dev_a2_token = self.dev_a2.issue_token()
        self.dev_a2.save(update_fields=["auth_token_hash"])
        dc = APIClient()
        dc.credentials(HTTP_AUTHORIZATION=f"Device {dev_a2_token}")
        dc.post("/api/v1/commands/acknowledge/", {"command_id": rel_cmd, "success": True}, format="json")

        self.dev_a2.refresh_from_db()
        self.assertEqual(self.dev_a2.enrollment_status, Device.Enrollment.RELEASED)
        self.assertEqual(self.dev_a2.ownership_status, Device.OwnershipStatus.RELEASED)
        self.assertIsNotNone(self.dev_a2.released_at)
        self.assertEqual(self.dev_a2.original_vendor_id, self.ven_a2.id)
        self.assertEqual(self.dev_a2.retailer_id, self.ret_a.id)
        self.assertEqual(self.dev_a2.customer_id, self.cust_a2.id)
        self.assertEqual(AccountProfile.objects.get(user=self.ven_a2).entitlements_consumed, 1)

    def test_panel_isolation(self):
        c = self._client(self.ven_a1)
        c.force_login(self.ven_a1)
        resp = c.get("/panel/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "dev-a1-0001")
        self.assertNotContains(resp, "dev-a2-0003")
        self.assertNotContains(resp, "dev-b1-0005")
        self.assertEqual(c.post(f"/panel/{self.dev_b1.id}/lock/").status_code, 403)
        self.assertEqual(c.get(f"/panel/qr/?session_id={self.sess_b1.id}").status_code, 403)

    def test_ownership_immutability_and_qr_secret_isolation(self):
        from django.core.exceptions import ValidationError

        # Ownership cannot be silently reassigned outside the transfer workflow
        dev = Device.objects.get(pk=self.dev_a1.id)
        dev.vendor = self.ven_a2
        with self.assertRaises(ValidationError):
            dev.save()
        dev = Device.objects.get(pk=self.dev_a1.id)
        dev.original_vendor = self.ven_b1
        with self.assertRaises(ValidationError):
            dev.save()
        dev = Device.objects.get(pk=self.dev_a1.id)
        dev.customer = self.cust_a2
        with self.assertRaises(ValidationError):
            dev.save()
        # Vendor must belong to the device's retailer
        dev = Device.objects.get(pk=self.dev_a1.id)
        dev.retailer = self.ret_b
        dev._transfer_authorized = True
        with self.assertRaises(ValidationError):
            dev.save()
        self.assertEqual(Device.objects.get(pk=self.dev_a1.id).vendor_id, self.ven_a1.id)

        # Vendors/retailers can never obtain the platform-wide static enrollment key via the panel QR
        va1 = self._client(self.ven_a1)
        va1.force_login(self.ven_a1)
        self.assertEqual(va1.get("/panel/qr/").status_code, 403)
        # A fresh own session QR embeds only that session's single-use token, never the static key
        er = va1.post("/api/v1/enrollments/", {"customer_name": "QR Test"}, format="json")
        sid, token = er.data["id"], er.data["enrollment_token"]
        qr = va1.get(f"/panel/qr/?session_id={sid}")
        self.assertEqual(qr.status_code, 200)
        self.assertNotIn("dev-enrollment-key", qr.content.decode())
        from devices.panel import provisioning_payload
        self.assertEqual(
            provisioning_payload("http://x", enrollment_key="abc")[
                "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE"]["enrollment_key"], "abc")
        self.assertEqual(EnrollmentSession.objects.get(pk=sid).get_raw_token(), token)
        # After use the QR is no longer retrievable
        APIClient().post("/api/v1/devices/register/", {"device_identifier": "dev-qr-used-01"},
                         format="json", HTTP_X_ENROLLMENT_TOKEN=token)
        self.assertEqual(EnrollmentSession.objects.get(pk=sid).token_encrypted, "")
        self.assertEqual(va1.get(f"/panel/qr/?session_id={sid}").status_code, 409)
        self.assertEqual(va1.get(f"/api/v1/enrollments/{sid}/qr/").status_code, 409)

        # Disabled vendor's pending enrollment token is rejected
        er2 = va1.post("/api/v1/enrollments/", {"customer_name": "Disabled"}, format="json")
        get_user_model().objects.filter(pk=self.ven_a1.pk).update(is_active=False)
        rr = APIClient().post("/api/v1/devices/register/", {"device_identifier": "dev-disabled-01"},
                              format="json", HTTP_X_ENROLLMENT_TOKEN=er2.data["enrollment_token"])
        self.assertEqual(rr.status_code, 403)

    def test_panel_and_api_quota_management(self):
        # Superuser can set quota on Retailer A and Vendor A1
        sc = self._client(self.su)
        r = sc.post(f"/api/v1/accounts/{self.ven_a1.id}/quota/", {"entitlement_quota": 25}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["entitlement_quota"], 25)

        # Retailer A can set quota on its own Vendor A1, but NOT on Retailer B's Vendor B1
        ra = self._client(self.ret_a)
        ra.force_login(self.ret_a)
        self.assertEqual(ra.post(f"/panel/accounts/{self.ven_a1.id}/quota/", {"entitlement_quota": "15"}).status_code, 302)
        self.assertEqual(AccountProfile.objects.get(user=self.ven_a1).entitlement_quota, 15)
        self.assertEqual(ra.post(f"/panel/accounts/{self.ven_b1.id}/quota/", {"entitlement_quota": "99"}).status_code, 403)
        self.assertEqual(ra.post(f"/api/v1/accounts/{self.ven_b1.id}/quota/", {"entitlement_quota": 99}, format="json").status_code, 403)

        # Panel enrollment creation works and displays one-time token
        er = ra.post("/panel/enrollments/create/", {"customer_name": "Panel Cust", "customer_mobile": "+919000011111"})
        self.assertEqual(er.status_code, 302)
        home = ra.get("/panel/")
        self.assertContains(home, "Enrollment Key Created")

        # Increase / decrease / remove device limit
        self.assertEqual(ra.post(f"/panel/accounts/{self.ven_a1.id}/quota/", {"delta": "3"}).status_code, 302)
        self.assertEqual(AccountProfile.objects.get(user=self.ven_a1).entitlement_quota, 18)
        self.assertEqual(ra.post(f"/panel/accounts/{self.ven_a1.id}/quota/", {"delta": "-5"}).status_code, 302)
        self.assertEqual(AccountProfile.objects.get(user=self.ven_a1).entitlement_quota, 13)
        self.assertEqual(ra.post(f"/panel/accounts/{self.ven_a1.id}/quota/", {"action": "remove"}).status_code, 302)
        self.assertIsNone(AccountProfile.objects.get(user=self.ven_a1).entitlement_quota)

        # Retailer A can create & delete a fresh vendor, but cannot delete Retailer B's vendor
        ra.post("/panel/rbac/account/", {
            "username": "temp_vendor_a",
            "password": "StrongPass!123",
            "account_type": "VENDOR",
            "entitlement_quota": "5",
        })
        temp_v = get_user_model().objects.get(username="temp_vendor_a")
        self.assertEqual(temp_v.profile.retailer_id, self.ret_a.id)
        self.assertEqual(ra.post(f"/panel/accounts/{self.ven_b1.id}/delete/").status_code, 403)
        self.assertEqual(ra.post(f"/panel/accounts/{temp_v.id}/delete/").status_code, 302)
        self.assertFalse(get_user_model().objects.filter(pk=temp_v.id).exists())
