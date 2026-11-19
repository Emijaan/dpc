from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import AccountProfile, Retailer, TenantStatus, Vendor
from audit.models import DeviceAuditLog
from roles.permissions import ensure_default_rbac


@override_settings(ALLOWED_HOSTS=["*"])
class ThreeLevelAccountHierarchyTests(TestCase):
    PW = "Str0ng-Pass-123"

    def setUp(self):
        cache.clear()
        ensure_default_rbac()
        U = get_user_model()
        self.su = U.objects.create_user("platform_su", password=self.PW, is_staff=True, is_superuser=True)
        AccountProfile.objects.create(user=self.su, account_type=AccountProfile.AccountType.SUPERUSER)

    def _auth(self, username, password=None):
        c = APIClient()
        r = c.post("/api/v1/auth/login/", {"username": username, "password": password or self.PW}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        return c

    def _create_retailer(self, su_client, username, business):
        return su_client.post(
            "/api/v1/retailers/",
            {
                "username": username,
                "password": self.PW,
                "full_name": f"{business} Owner",
                "business_name": business,
                "address": "123 Market St",
                "contact_person": "Alice",
                "mobile": "+919876543210",
                "email": f"{username}@example.com",
                "entitlement_quota": 25,
            },
            format="json",
        )

    def test_1_to_6_hierarchy_creation_editing_activation_and_isolation(self):
        su = self._auth("platform_su")

        # 1. Superuser can create Retailers
        ra_resp = self._create_retailer(su, "ret_a", "Acme Finance")
        self.assertEqual(ra_resp.status_code, 201, ra_resp.data)
        rb_resp = self._create_retailer(su, "ret_b", "Zenith Mobiles")
        self.assertEqual(rb_resp.status_code, 201, rb_resp.data)
        ret_a_id = ra_resp.data["id"]
        ret_b_id = rb_resp.data["id"]
        self.assertEqual(Retailer.objects.count(), 2)

        # Superuser can edit Retailer details
        patch_ra = su.patch(
            f"/api/v1/retailers/{ret_a_id}/",
            {"business_name": "Acme Finance Ltd", "contact_person": "A. Verma"},
            format="json",
        )
        self.assertEqual(patch_ra.status_code, 200)
        self.assertEqual(patch_ra.data["business_name"], "Acme Finance Ltd")

        # 2. Superuser can create Vendors under a Retailer
        va1_resp = su.post(
            "/api/v1/vendors/",
            {
                "username": "ven_a1",
                "password": self.PW,
                "retailer_profile_id": ret_a_id,
                "full_name": "City Owner",
                "business_name": "City Mobiles",
                "address": "Shop 4",
                "contact_person": "Bob",
                "mobile": "+919111111111",
                "email": "ven_a1@example.com",
                "entitlement_quota": 5,
            },
            format="json",
        )
        self.assertEqual(va1_resp.status_code, 201, va1_resp.data)
        ven_a1_id = va1_resp.data["id"]
        ven_a1_acct = va1_resp.data["account_id"]

        # 3. Retailer A can create its own Vendors
        ra = self._auth("ret_a")
        va2_resp = ra.post(
            "/api/v1/vendors/",
            {
                "username": "ven_a2",
                "password": self.PW,
                "full_name": "Metro Owner",
                "business_name": "Metro Phones",
                "address": "Shop 9",
                "contact_person": "Carol",
                "mobile": "+919222222222",
                "email": "ven_a2@example.com",
                "entitlement_quota": 10,
            },
            format="json",
        )
        self.assertEqual(va2_resp.status_code, 201, va2_resp.data)
        self.assertEqual(va2_resp.data["retailer_id"], ret_a_id)

        # Retailer B creates Vendor B1
        rb = self._auth("ret_b")
        vb1_resp = rb.post(
            "/api/v1/vendors/",
            {
                "username": "ven_b1",
                "password": self.PW,
                "full_name": "Star Owner",
                "business_name": "Star Telecom",
                "contact_person": "Dan",
                "mobile": "+919333333333",
                "email": "ven_b1@example.com",
            },
            format="json",
        )
        self.assertEqual(vb1_resp.status_code, 201, vb1_resp.data)
        ven_b1_id = vb1_resp.data["id"]
        ven_b1_acct = vb1_resp.data["account_id"]

        # 5. Retailer A cannot access or modify Retailer B or Retailer B's Vendors
        self.assertEqual(ra.get(f"/api/v1/retailers/{ret_b_id}/").status_code, 403)
        self.assertEqual(ra.patch(f"/api/v1/retailers/{ret_b_id}/", {"business_name": "Hack"}, format="json").status_code, 403)
        self.assertEqual(ra.post(f"/api/v1/retailers/", {"username": "x", "password": self.PW}, format="json").status_code, 403)
        self.assertEqual(ra.get(f"/api/v1/vendors/{ven_b1_id}/").status_code, 403)
        self.assertEqual(ra.patch(f"/api/v1/vendors/{ven_b1_id}/", {"business_name": "Hack"}, format="json").status_code, 403)
        self.assertEqual(ra.post(f"/api/v1/accounts/{ven_b1_acct}/deactivate/").status_code, 403)
        self.assertEqual(ra.post("/api/v1/vendors/", {
            "username": "cross_v", "password": self.PW, "retailer_profile_id": ret_b_id,
            "full_name": "X", "business_name": "X", "contact_person": "X", "mobile": "123", "email": "x@x.com"
        }, format="json").status_code, 403)
        # Retailer list only contains Retailer A
        self.assertEqual([r["id"] for r in ra.get("/api/v1/retailers/").data["retailers"]], [ret_a_id])
        # Retailer A's vendor list only contains Vendor A1 & A2
        self.assertEqual(
            {v["username"] for v in ra.get("/api/v1/vendors/").data["vendors"]},
            {"ven_a1", "ven_a2"},
        )

        # 4 & 6. Vendor A1 cannot create another account level and cannot access Vendor B1 or Vendor A2
        va1 = self._auth("ven_a1")
        self.assertEqual(va1.post("/api/v1/accounts/", {
            "username": "sub_vendor", "password": self.PW, "account_type": "VENDOR"
        }, format="json").status_code, 403)
        self.assertEqual(va1.post("/api/v1/vendors/", {
            "username": "sub_vendor", "password": self.PW,
            "full_name": "X", "business_name": "X", "contact_person": "X", "mobile": "123", "email": "x@x.com"
        }, format="json").status_code, 403)
        self.assertEqual(va1.get("/api/v1/retailers/").status_code, 403)
        self.assertEqual(va1.get(f"/api/v1/vendors/{ven_a1_id}/").status_code, 200)
        self.assertEqual(va1.get(f"/api/v1/vendors/{ven_b1_id}/").status_code, 403)
        self.assertEqual(va1.get(f"/api/v1/accounts/{ven_b1_acct}/").status_code, 403)
        self.assertEqual(va1.get(f"/api/v1/accounts/{ven_a1_acct}/").status_code, 200)

        # Activate / Deactivate syncs User.is_active & Vendor.status and blocks login
        self.assertEqual(ra.post(f"/api/v1/accounts/{ven_a1_acct}/deactivate/").status_code, 200)
        v_rec = Vendor.objects.get(pk=ven_a1_id)
        self.assertEqual(v_rec.status, TenantStatus.INACTIVE)
        self.assertFalse(v_rec.account.is_active)
        self.assertEqual(
            APIClient().post("/api/v1/auth/login/", {"username": "ven_a1", "password": self.PW}, format="json").status_code,
            401,
        )
        self.assertEqual(ra.post(f"/api/v1/accounts/{ven_a1_acct}/activate/").status_code, 200)
        v_rec.refresh_from_db()
        self.assertEqual(v_rec.status, TenantStatus.ACTIVE)
        self.assertTrue(v_rec.account.is_active)

        # Unauthorized access attempts were audited
        self.assertTrue(DeviceAuditLog.objects.filter(event="UNAUTHORIZED_ACCESS_ATTEMPT").exists())

    def test_disable_and_delete_retailer_and_vendor_entitlement_rules(self):
        su = self._auth("platform_su")
        # Create Retailer A with 10 keys, allocate 4 to Vendor A1 (6 unallocated remain on Retailer A)
        ra_resp = self._create_retailer(su, "ret_rule_a", "Rule Ret A").data
        ret_a_id = ra_resp["id"]
        ret_a_acct = ra_resp["account_id"]
        su.post("/api/v1/entitlements/allocate/", {"recipient_id": ret_a_acct, "quantity": 10}, format="json")

        ra = self._auth("ret_rule_a")
        va1_resp = ra.post(
            "/api/v1/vendors/",
            {
                "username": "ven_rule_a1", "password": self.PW,
                "full_name": "V1", "business_name": "Ven Rule A1",
                "contact_person": "V1", "mobile": "+919000000001", "email": "v1@example.com",
            },
            format="json",
        ).data
        ven_a1_id = va1_resp["id"]
        ven_a1_acct = va1_resp["account_id"]
        ra.post("/api/v1/entitlements/allocate/", {"recipient_id": ven_a1_acct, "quantity": 4}, format="json")

        # Superuser can edit Vendor directly
        self.assertEqual(
            su.patch(f"/api/v1/vendors/{ven_a1_id}/", {"business_name": "Ven Rule A1 Edited"}, format="json").status_code,
            200,
        )
        # Retailer can edit its own Vendor
        self.assertEqual(
            ra.patch(f"/api/v1/vendors/{ven_a1_id}/", {"contact_person": "Updated Contact"}, format="json").status_code,
            200,
        )

        # Disabling Retailer A disables Retailer A's 6 unallocated keys, while Vendor A1's 4 keys stay ACTIVE & usable
        self.assertEqual(su.post(f"/api/v1/accounts/{ret_a_acct}/deactivate/").status_code, 200)
        self.assertEqual(su.get(f"/api/v1/entitlements/balance/?account_id={ret_a_acct}").data["available"], 0)
        self.assertEqual(su.get(f"/api/v1/entitlements/balance/?account_id={ven_a1_acct}").data["available"], 4)

        # Vendor A1 can still enroll using its already-allocated key
        va1 = self._auth("ven_rule_a1")
        er = va1.post("/api/v1/enrollments/", {"customer_name": "After Ret Disable"}, format="json")
        self.assertEqual(er.status_code, 201)
        self.assertEqual(
            APIClient().post(
                "/api/v1/devices/register/",
                {"device_identifier": "dev-after-ret-disable"},
                format="json",
                HTTP_X_ENROLLMENT_TOKEN=er.data["enrollment_token"],
            ).status_code,
            201,
        )
        self.assertEqual(va1.get("/api/v1/entitlements/balance/").data["available"], 3)

        # Deleting Retailer A preserves Vendor A1's allocated keys & device history, keeping Retailer A disabled
        del_r = su.delete(f"/api/v1/retailers/{ret_a_id}/")
        self.assertEqual(del_r.status_code, 200)
        self.assertEqual(va1.get("/api/v1/entitlements/balance/").data["available"], 3)

        # Disabling Vendor A1 invalidates ALL of Vendor A1's remaining keys and revokes pending enrollments
        er_pending = va1.post("/api/v1/enrollments/", {"customer_name": "Before Ven Disable"}, format="json")
        self.assertEqual(er_pending.status_code, 201)
        self.assertEqual(su.post(f"/api/v1/accounts/{ven_a1_acct}/deactivate/").status_code, 200)
        self.assertEqual(su.get(f"/api/v1/entitlements/balance/?account_id={ven_a1_acct}").data["available"], 0)
        self.assertEqual(
            APIClient().post(
                "/api/v1/devices/register/",
                {"device_identifier": "dev-after-ven-disable"},
                format="json",
                HTTP_X_ENROLLMENT_TOKEN=er_pending.data["enrollment_token"],
            ).status_code,
            403,
        )

        # Unused Retailer & unused Vendor can be hard-deleted (204)
        ret_unused = self._create_retailer(su, "ret_unused", "Unused Ret").data
        su.post("/api/v1/entitlements/allocate/", {"recipient_id": ret_unused["account_id"], "quantity": 5}, format="json")
        self.assertEqual(su.delete(f"/api/v1/retailers/{ret_unused['id']}/").status_code, 204)

        ret_b = self._create_retailer(su, "ret_rule_b", "Rule Ret B").data
        rb = self._auth("ret_rule_b")
        ven_unused = rb.post(
            "/api/v1/vendors/",
            {
                "username": "ven_unused", "password": self.PW,
                "full_name": "VU", "business_name": "Ven Unused",
                "contact_person": "VU", "mobile": "+919000000002", "email": "vu@example.com",
            },
            format="json",
        ).data
        self.assertEqual(rb.delete(f"/api/v1/vendors/{ven_unused['id']}/").status_code, 204)
