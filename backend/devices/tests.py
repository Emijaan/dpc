import base64
from datetime import timedelta

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from commands import signing
from commands.models import DeviceCommand
from devices.models import Device

KEY = {"HTTP_X_ENROLLMENT_KEY": "dev-enrollment-key"}


def register(client, ident="test-device-0001"):
    r = client.post("/api/v1/devices/register/", {"device_identifier": ident, "manufacturer": "vivo",
                    "model": "1902", "android_version": "9", "sdk_version": 28, "app_version": "0.1"},
                    format="json", **KEY)
    return r


@override_settings(ENROLLMENT_KEY="dev-enrollment-key", ALLOWED_HOSTS=["*"])
class ApiFlowTests(TestCase):
    def setUp(self):
        self.op = APIClient()
        u = get_user_model().objects.create_user("op", password="x-strong-pass-123", is_staff=True)
        self.op.force_authenticate(u)
        self.dev = APIClient()
        r = register(self.dev)
        self.assertEqual(r.status_code, 201)
        self.device_id = r.data["device_id"]
        self.dev.credentials(HTTP_AUTHORIZATION="Device " + r.data["device_token"])

    def test_register_requires_enrollment_key(self):
        r = APIClient().post("/api/v1/devices/register/", {"device_identifier": "other-device-01"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_duplicate_registration_rejected(self):
        self.assertEqual(register(APIClient()).status_code, 409)

    def test_device_endpoints_need_credential(self):
        self.assertIn(APIClient().get("/api/v1/commands/pending/").status_code, (401, 403))
        bad = APIClient(); bad.credentials(HTTP_AUTHORIZATION="Device nope")
        self.assertEqual(bad.get("/api/v1/commands/pending/").status_code, 401)

    def test_device_cannot_use_operator_endpoints(self):
        self.assertEqual(self.dev.post(f"/api/v1/devices/{self.device_id}/lock/").status_code, 403)

    def test_lock_flow_signature_and_ack(self):
        r = self.op.post(f"/api/v1/devices/{self.device_id}/lock/", {"reason": "test"}, format="json")
        self.assertEqual(r.status_code, 201)
        p = self.dev.get("/api/v1/commands/pending/").data["commands"]
        self.assertEqual(len(p), 1)
        c = p[0]
        # Verify the signature like the Android app will.
        pub = serialization.load_der_public_key(base64.b64decode(signing.public_key_b64()))
        payload = "|".join([c["command_id"], c["device_id"], c["command_type"], str(c["issued_at"]),
                            str(c["expires_at"]), c["nonce"], c["reason"]]).encode()
        pub.verify(base64.b64decode(c["signature"]), payload, ec.ECDSA(hashes.SHA256()))
        # Not shown as locked until device reports success.
        self.assertEqual(Device.objects.get(pk=self.device_id).restriction_status, "NONE")
        ack = self.dev.post("/api/v1/commands/acknowledge/",
                            {"command_id": c["command_id"], "success": True, "result": "ok"}, format="json")
        self.assertEqual(ack.data["status"], "EXECUTED")
        self.assertEqual(Device.objects.get(pk=self.device_id).restriction_status, "LOCKED")
        again = self.dev.post("/api/v1/commands/acknowledge/",
                              {"command_id": c["command_id"], "success": False}, format="json")
        self.assertTrue(again.data["duplicate"])
        self.assertEqual(Device.objects.get(pk=self.device_id).restriction_status, "LOCKED")

    def test_duplicate_lock_command_not_created(self):
        self.op.post(f"/api/v1/devices/{self.device_id}/lock/")
        r = self.op.post(f"/api/v1/devices/{self.device_id}/lock/")
        self.assertTrue(r.data["duplicate"])
        self.assertEqual(DeviceCommand.objects.count(), 1)

    def test_expired_command_not_delivered(self):
        self.op.post(f"/api/v1/devices/{self.device_id}/lock/")
        DeviceCommand.objects.update(expires_at=timezone.now() - timedelta(seconds=5))
        self.assertEqual(self.dev.get("/api/v1/commands/pending/").data["commands"], [])
        self.assertEqual(DeviceCommand.objects.get().command_status, "EXPIRED")

    def test_offline_command_waits_then_delivered(self):
        Device.objects.update(last_seen=timezone.now() - timedelta(hours=2))
        r = self.op.post(f"/api/v1/devices/{self.device_id}/lock/")
        self.assertFalse(r.data["device_online"])
        self.assertEqual(DeviceCommand.objects.get().command_status, "PENDING")
        self.assertEqual(len(self.dev.get("/api/v1/commands/pending/").data["commands"]), 1)

    def test_other_device_cannot_ack(self):
        r = self.op.post(f"/api/v1/devices/{self.device_id}/lock/")
        other = APIClient()
        rr = register(other, "test-device-0002")
        other.credentials(HTTP_AUTHORIZATION="Device " + rr.data["device_token"])
        ack = other.post("/api/v1/commands/acknowledge/",
                         {"command_id": r.data["command_id"], "success": True}, format="json")
        self.assertEqual(ack.status_code, 404)

    def test_release_revokes_device(self):
        r = self.op.post(f"/api/v1/devices/{self.device_id}/release/")
        self.dev.post("/api/v1/commands/acknowledge/",
                      {"command_id": r.data["command_id"], "success": True}, format="json")
        self.assertEqual(Device.objects.get(pk=self.device_id).enrollment_status, "RELEASED")
        self.assertEqual(self.dev.get("/api/v1/commands/pending/").status_code, 401)

    def test_renew_token_invalidates_old(self):
        old = self.dev._credentials["HTTP_AUTHORIZATION"]
        new = self.dev.post("/api/v1/devices/renew-token/").data["device_token"]
        c = APIClient(); c.credentials(HTTP_AUTHORIZATION=old)
        self.assertEqual(c.get("/api/v1/devices/status/").status_code, 401)
        c.credentials(HTTP_AUTHORIZATION="Device " + new)
        self.assertEqual(c.get("/api/v1/devices/status/").status_code, 200)

    def test_panel_requires_staff(self):
        self.assertEqual(self.client.get("/panel/").status_code, 302)

    def test_audit_trail(self):
        self.op.post(f"/api/v1/devices/{self.device_id}/lock/")
        self.dev.get("/api/v1/commands/pending/")
        from audit.models import DeviceAuditLog
        events = set(DeviceAuditLog.objects.values_list("event", flat=True))
        self.assertTrue({"DEVICE_REGISTERED", "COMMAND_CREATED", "COMMAND_DELIVERED"} <= events)

    def test_qr_provisioning_payload_and_page(self):
        from devices.panel import provisioning_payload
        with self.settings(APK_CERT_SHA256="abc123_checksum", PUBLIC_BASE_URL="https://dpc.apinfotechandcybersolution.com"):
            p = provisioning_payload()
            self.assertEqual(
                p["android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME"],
                "com.akdevicelock.dpc/com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver",
            )
            self.assertEqual(
                p["android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION"],
                "https://dpc.apinfotechandcybersolution.com/download/akdevicelock.apk",
            )
            self.assertEqual(
                p["android.app.extra.PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM"],
                "abc123_checksum",
            )
            self.assertEqual(
                p["android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE"]["server_url"],
                "https://dpc.apinfotechandcybersolution.com",
            )
            self.client.force_login(get_user_model().objects.get(username="op"))
            resp = self.client.get("/panel/qr/")
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"<svg", resp.content)

    def test_api_docs_endpoint(self):
        resp = self.client.get("/api/v1/docs/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        paths = {e["path"] for e in data["endpoints"]}
        self.assertIn("/api/v1/devices/register/", paths)
        self.assertIn("/api/v1/commands/pending/", paths)

    def test_fcm_noop_when_unconfigured(self):
        from notifications.services import notify_commands_available
        dev = Device.objects.get(pk=self.device_id)
        self.assertFalse(notify_commands_available(dev))
