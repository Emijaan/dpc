from datetime import timedelta
import threading

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountProfile
from accounts.services import create_account_with_profile
from commands.models import DeviceCommand
from devices.models import Device
from entitlements.models import EntitlementAllocation, EntitlementConsumption, EntitlementTransfer
from roles.permissions import ensure_default_rbac


@override_settings(ALLOWED_HOSTS=["*"])
class EntitlementLedgerTests(TestCase):
    PW = "Str0ng-Pass-123"

    def setUp(self):
        cache.clear()
        ensure_default_rbac()
        U = get_user_model()
        self.su = U.objects.create_user("ent_su", password=self.PW, is_staff=True, is_superuser=True)
        AccountProfile.objects.create(user=self.su, account_type=AccountProfile.AccountType.SUPERUSER)

        self.ret_a = create_account_with_profile(
            created_by=self.su, username="ent_ret_a", password=self.PW,
            account_type=AccountProfile.AccountType.RETAILER, business_name="Ret A",
        )
        self.ret_b = create_account_with_profile(
            created_by=self.su, username="ent_ret_b", password=self.PW,
            account_type=AccountProfile.AccountType.RETAILER, business_name="Ret B",
        )
        self.ven_a1 = create_account_with_profile(
            created_by=self.su, username="ent_ven_a1", password=self.PW,
            account_type=AccountProfile.AccountType.VENDOR, retailer_user=self.ret_a, business_name="Ven A1",
        )
        self.ven_a2 = create_account_with_profile(
            created_by=self.su, username="ent_ven_a2", password=self.PW,
            account_type=AccountProfile.AccountType.VENDOR, retailer_user=self.ret_a, business_name="Ven A2",
        )
        self.ven_b1 = create_account_with_profile(
            created_by=self.su, username="ent_ven_b1", password=self.PW,
            account_type=AccountProfile.AccountType.VENDOR, retailer_user=self.ret_b, business_name="Ven B1",
        )

    def _auth(self, username):
        c = APIClient()
        r = c.post("/api/v1/auth/login/", {"username": username, "password": self.PW}, format="json")
        self.assertEqual(r.status_code, 200)
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        return c

    def test_17_to_21_allocate_distribute_transfer_and_cross_retailer_blocked(self):
        su = self._auth("ent_su")
        ra = self._auth("ent_ret_a")
        va1 = self._auth("ent_ven_a1")

        # 17. Superuser allocates 10 to Retailer A (365-day validity)
        r = su.post("/api/v1/entitlements/allocate/", {"recipient_id": self.ret_a.id, "quantity": 10}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["recipient_balance"]["available"], 10)
        alloc = EntitlementAllocation.objects.get(allocated_to=self.ret_a)
        self.assertEqual((alloc.expires_at - alloc.issued_at).days, 365)

        # 18. Retailer A allocates 5 to Vendor A1 (cannot exceed 10)
        self.assertEqual(
            ra.post("/api/v1/entitlements/allocate/", {"recipient_id": self.ven_a1.id, "quantity": 11}, format="json").status_code,
            400,
        )
        r2 = ra.post("/api/v1/entitlements/allocate/", {"recipient_id": self.ven_a1.id, "quantity": 5}, format="json")
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r2.data["recipient_balance"]["available"], 5)
        self.assertEqual(ra.get("/api/v1/entitlements/balance/").data["available"], 5)
        self.assertEqual(ra.get("/api/v1/entitlements/balance/").data["distributed"], 5)

        # Retailer A cannot allocate to Retailer B's Vendor B1
        self.assertEqual(
            ra.post("/api/v1/entitlements/allocate/", {"recipient_id": self.ven_b1.id, "quantity": 1}, format="json").status_code,
            403,
        )

        # 19. Vendor A1 transfers 2 unused entitlements to Vendor A2
        tr = va1.post(
            "/api/v1/entitlements/transfer/",
            {"receiver_id": self.ven_a2.id, "quantity": 2, "reason": "rebalance"},
            format="json",
        )
        self.assertEqual(tr.status_code, 201, tr.data)
        self.assertEqual(tr.data["sender_balance"]["available"], 3)
        self.assertEqual(tr.data["receiver_balance"]["available"], 2)
        # Retailer A's retained balance remains 5
        self.assertEqual(ra.get("/api/v1/entitlements/balance/").data["available"], 5)

        # 20. Cross-Retailer transfer to Vendor B1 is blocked
        self.assertEqual(
            va1.post("/api/v1/entitlements/transfer/", {"receiver_id": self.ven_b1.id, "quantity": 1}, format="json").status_code,
            403,
        )

        # 21. Consumed entitlements cannot be transferred
        er = va1.post("/api/v1/enrollments/", {"customer_name": "Cust 1"}, format="json")
        self.assertEqual(er.status_code, 201)
        tok = er.data["enrollment_token"]
        self.assertEqual(
            APIClient().post("/api/v1/devices/register/", {"device_identifier": "ent-dev-0001"},
                             format="json", HTTP_X_ENROLLMENT_TOKEN=tok).status_code,
            201,
        )
        # Vendor A1 had 3 available, 1 consumed -> only 2 unused left; transferring 3 must fail
        self.assertEqual(va1.get("/api/v1/entitlements/balance/").data["available"], 2)
        self.assertEqual(va1.get("/api/v1/entitlements/balance/").data["consumed"], 1)
        self.assertEqual(
            va1.post("/api/v1/entitlements/transfer/", {"receiver_id": self.ven_a2.id, "quantity": 3}, format="json").status_code,
            400,
        )

    def test_23_to_27_qr_failed_consume_release_and_expiry(self):
        su = self._auth("ent_su")
        va1 = self._auth("ent_ven_a1")
        su.post("/api/v1/entitlements/allocate/", {"recipient_id": self.ven_a1.id, "quantity": 1}, format="json")

        # 23. Creating enrollment session & fetching QR does NOT consume an entitlement
        er = va1.post(
            "/api/v1/enrollments/",
            {"customer_name": "Cust QR", "intended_device_identifier": "expected-dev-01"},
            format="json",
        )
        self.assertEqual(er.status_code, 201)
        sid, tok = er.data["id"], er.data["enrollment_token"]
        self.assertEqual(va1.get(f"/api/v1/enrollments/{sid}/qr/").status_code, 200)
        self.assertEqual(va1.get("/api/v1/entitlements/balance/").data["available"], 1)
        self.assertEqual(va1.get("/api/v1/entitlements/balance/").data["consumed"], 0)

        # 24. Failed enrollment does NOT consume an entitlement
        bad = APIClient().post(
            "/api/v1/devices/register/",
            {"device_identifier": "wrong-dev-99"},
            format="json",
            HTTP_X_ENROLLMENT_TOKEN=tok,
        )
        self.assertEqual(bad.status_code, 403)
        self.assertEqual(va1.get("/api/v1/entitlements/balance/").data["available"], 1)
        self.assertEqual(va1.get("/api/v1/entitlements/balance/").data["consumed"], 0)

        # 25. Successful registration consumes exactly 1 entitlement & writes append-only consumption
        ok = APIClient().post(
            "/api/v1/devices/register/",
            {"device_identifier": "expected-dev-01"},
            format="json",
            HTTP_X_ENROLLMENT_TOKEN=tok,
        )
        self.assertEqual(ok.status_code, 201)
        self.assertEqual(va1.get("/api/v1/entitlements/balance/").data["available"], 0)
        self.assertEqual(va1.get("/api/v1/entitlements/balance/").data["consumed"], 1)
        cons = EntitlementConsumption.objects.get(device_id=ok.data["device_id"])
        with self.assertRaises(ValidationError):
            cons.delete()

        # 26. Releasing the device never restores the consumed entitlement
        dev_id = ok.data["device_id"]
        rel = su.post(f"/api/v1/devices/{dev_id}/release/")
        self.assertEqual(rel.status_code, 201)
        dc = APIClient()
        dc.credentials(HTTP_AUTHORIZATION="Device " + ok.data["device_token"])
        dc.post("/api/v1/commands/acknowledge/", {"command_id": rel.data["command_id"], "success": True}, format="json")
        self.assertEqual(Device.objects.get(pk=dev_id).enrollment_status, Device.Enrollment.RELEASED)
        self.assertEqual(va1.get("/api/v1/entitlements/balance/").data["available"], 0)
        self.assertEqual(va1.get("/api/v1/entitlements/balance/").data["consumed"], 1)

        # 27. Expired allocations cannot be used for new registrations, but do not lock/block existing devices
        su.post("/api/v1/entitlements/allocate/", {"recipient_id": self.ven_a2.id, "quantity": 2}, format="json")
        va2 = self._auth("ent_ven_a2")
        er2 = va2.post("/api/v1/enrollments/", {"customer_name": "Pre-expiry"}, format="json")
        tok_ok = er2.data["enrollment_token"]
        reg_ok = APIClient().post(
            "/api/v1/devices/register/",
            {"device_identifier": "pre-exp-dev-01"},
            format="json",
            HTTP_X_ENROLLMENT_TOKEN=tok_ok,
        )
        self.assertEqual(reg_ok.status_code, 201)

        # Expire Vendor A2's allocation
        EntitlementAllocation.objects.filter(allocated_to=self.ven_a2).update(
            expires_at=timezone.now() - timedelta(minutes=5)
        )
        self.assertEqual(va2.get("/api/v1/entitlements/balance/").data["available"], 0)
        self.assertEqual(
            va2.post("/api/v1/enrollments/", {"customer_name": "Post-expiry"}, format="json").status_code,
            403,
        )
        # Existing registered device can still be unlocked/released by authorized operator
        self.assertEqual(va2.post(f"/api/v1/devices/{reg_ok.data['device_id']}/unlock/").status_code, 201)


@override_settings(ALLOWED_HOSTS=["*"])
class EntitlementConcurrencyTests(TransactionTestCase):
    PW = "Str0ng-Pass-123"

    def test_22_concurrent_registrations_cannot_double_consume(self):
        ensure_default_rbac()
        U = get_user_model()
        su = U.objects.create_user("conc_su", password=self.PW, is_staff=True, is_superuser=True)
        AccountProfile.objects.create(user=su, account_type=AccountProfile.AccountType.SUPERUSER)
        ret = create_account_with_profile(
            created_by=su, username="conc_ret", password=self.PW,
            account_type=AccountProfile.AccountType.RETAILER, business_name="Conc Ret",
        )
        ven = create_account_with_profile(
            created_by=su, username="conc_ven", password=self.PW,
            account_type=AccountProfile.AccountType.VENDOR, retailer_user=ret,
            business_name="Conc Ven", entitlement_quota=1,
        )
        vc = APIClient()
        login = vc.post("/api/v1/auth/login/", {"username": "conc_ven", "password": self.PW}, format="json")
        vc.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        t1 = vc.post("/api/v1/enrollments/", {"customer_name": "Race 1"}, format="json").data["enrollment_token"]
        t2 = vc.post("/api/v1/enrollments/", {"customer_name": "Race 2"}, format="json").data["enrollment_token"]

        results = []
        barrier = threading.Barrier(2)

        def register_one(idx, tok):
            try:
                barrier.wait(timeout=5)
                r = APIClient().post(
                    "/api/v1/devices/register/",
                    {"device_identifier": f"race-device-00{idx}"},
                    format="json",
                    HTTP_X_ENROLLMENT_TOKEN=tok,
                )
                results.append(r.status_code)
            finally:
                connections.close_all()

        th1 = threading.Thread(target=register_one, args=(1, t1))
        th2 = threading.Thread(target=register_one, args=(2, t2))
        th1.start(); th2.start()
        th1.join(); th2.join()

        self.assertEqual(sorted(results), [201, 403])
        alloc = EntitlementAllocation.objects.get(allocated_to=ven)
        self.assertEqual(alloc.consumed_quantity, 1)
        self.assertEqual(alloc.available_quantity, 0)
        self.assertEqual(EntitlementConsumption.objects.count(), 1)
