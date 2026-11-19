from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import AccountProfile, Retailer, TenantStatus, Vendor
from accounts.services import (
    create_account_with_profile,
    delete_or_disable_account,
    set_account_active,
    update_tenant_profile,
)
from audit.models import log_event
from devices.ownership import (
    can_access_retailer,
    can_access_vendor,
    can_manage_account,
    can_view_account,
    get_account_type,
    is_superuser_account,
    scope_accounts_queryset,
    scope_retailers_queryset,
    scope_vendors_queryset,
)
from roles.models import Role
from roles.permissions import HasPermissionCode, ensure_default_rbac, user_has_perm


def account_dict(u) -> dict:
    prof = getattr(u, "profile", None)
    ret_prof = getattr(u, "retailer_profile", None)
    ven_prof = getattr(u, "vendor_profile", None)
    tenant = ret_prof or ven_prof
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "is_active": u.is_active,
        "is_superuser": u.is_superuser,
        "account_type": get_account_type(u) or (prof.account_type if prof else None),
        "retailer_id": prof.retailer_id if prof else None,
        "retailer_profile_id": str(ret_prof.id) if ret_prof else (str(ven_prof.retailer_id) if ven_prof else None),
        "vendor_profile_id": str(ven_prof.id) if ven_prof else None,
        "full_name": tenant.full_name if tenant else u.get_full_name(),
        "business_name": tenant.business_name if tenant else "",
        "contact_person": tenant.contact_person if tenant else "",
        "address": tenant.address if tenant else "",
        "mobile": tenant.mobile if tenant else "",
        "status": tenant.status if tenant else (TenantStatus.ACTIVE if u.is_active else TenantStatus.INACTIVE),
        "entitlement_quota": prof.entitlement_quota if prof else None,
        "entitlements_consumed": prof.entitlements_consumed if prof else 0,
        "roles": list(u.account_roles.values_list("role__name", flat=True)),
        "created_at": u.date_joined.isoformat(),
    }


def retailer_dict(r: Retailer) -> dict:
    prof = getattr(r.account, "profile", None)
    return {
        "id": str(r.id),
        "account_id": r.account_id,
        "username": r.account.username,
        "full_name": r.full_name,
        "business_name": r.business_name,
        "contact_person": r.contact_person,
        "address": r.address,
        "mobile": r.mobile,
        "email": r.email,
        "status": r.status,
        "is_active": r.account.is_active,
        "entitlement_quota": prof.entitlement_quota if prof else None,
        "entitlements_consumed": prof.entitlements_consumed if prof else 0,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }


def vendor_dict(v: Vendor) -> dict:
    prof = getattr(v.account, "profile", None)
    return {
        "id": str(v.id),
        "account_id": v.account_id,
        "username": v.account.username,
        "retailer_id": str(v.retailer_id),
        "retailer_account_id": v.retailer.account_id,
        "retailer_business_name": v.retailer.business_name,
        "full_name": v.full_name,
        "business_name": v.business_name,
        "contact_person": v.contact_person,
        "address": v.address,
        "mobile": v.mobile,
        "email": v.email,
        "status": v.status,
        "is_active": v.account.is_active,
        "entitlement_quota": prof.entitlement_quota if prof else None,
        "entitlements_consumed": prof.entitlements_consumed if prof else 0,
        "created_at": v.created_at.isoformat(),
        "updated_at": v.updated_at.isoformat(),
    }


class AccountCreateSerializer(serializers.Serializer):
    username = serializers.RegexField(r"^[A-Za-z0-9_.\-@]{3,64}$")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    password = serializers.CharField(min_length=8, max_length=128)
    role_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    account_type = serializers.ChoiceField(
        choices=AccountProfile.AccountType.choices,
        required=False,
        default=AccountProfile.AccountType.VENDOR,
    )
    retailer_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    entitlement_quota = serializers.IntegerField(min_value=0, required=False, allow_null=True, default=None)
    full_name = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    business_name = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    contact_person = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    address = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    mobile = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(choices=TenantStatus.choices, required=False, default=TenantStatus.ACTIVE)


class AccountUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    full_name = serializers.CharField(max_length=128, required=False, allow_blank=True)
    business_name = serializers.CharField(max_length=160, required=False, allow_blank=True)
    contact_person = serializers.CharField(max_length=128, required=False, allow_blank=True)
    address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    mobile = serializers.CharField(max_length=32, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=TenantStatus.choices, required=False)


class TenantCreateSerializer(serializers.Serializer):
    username = serializers.RegexField(r"^[A-Za-z0-9_.\-@]{3,64}$")
    password = serializers.CharField(min_length=8, max_length=128)
    full_name = serializers.CharField(max_length=128)
    business_name = serializers.CharField(max_length=160)
    address = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    contact_person = serializers.CharField(max_length=128)
    mobile = serializers.CharField(max_length=32)
    email = serializers.EmailField()
    entitlement_quota = serializers.IntegerField(min_value=0, required=False, allow_null=True, default=None)
    status = serializers.ChoiceField(choices=TenantStatus.choices, required=False, default=TenantStatus.ACTIVE)


class VendorCreateSerializer(TenantCreateSerializer):
    retailer_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    retailer_profile_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class TenantUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=128, required=False)
    business_name = serializers.CharField(max_length=160, required=False)
    address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    contact_person = serializers.CharField(max_length=128, required=False)
    mobile = serializers.CharField(max_length=32, required=False)
    email = serializers.EmailField(required=False)
    status = serializers.ChoiceField(choices=TenantStatus.choices, required=False)


class AccountListCreateView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "accounts.manage"

    def get(self, request):
        qs = scope_accounts_queryset(request.user).select_related(
            "profile", "retailer_profile", "vendor_profile"
        ).order_by("id")
        return Response({"accounts": [account_dict(u) for u in qs]})

    def post(self, request):
        ensure_default_rbac()
        s = AccountCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        U = get_user_model()
        if U.objects.filter(username=d["username"]).exists():
            return Response({"error": "username_exists"}, status=status.HTTP_409_CONFLICT)

        actor_type = get_account_type(request.user)
        target_type = d["account_type"]
        retailer_obj = None

        if actor_type == AccountProfile.AccountType.RETAILER:
            if target_type != AccountProfile.AccountType.VENDOR:
                log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", "retailer_create_non_vendor", request=request)
                return Response({"error": "retailer_can_only_create_vendors"}, status=status.HTTP_403_FORBIDDEN)
            if d["retailer_id"] is not None and d["retailer_id"] != request.user.id:
                log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", "retailer_cross_tenant_vendor", request=request)
                return Response({"error": "cannot_assign_other_retailer"}, status=status.HTTP_403_FORBIDDEN)
            retailer_obj = request.user
        elif actor_type != AccountProfile.AccountType.SUPERUSER:
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", "non_privileged_account_create", request=request)
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        else:
            if target_type == AccountProfile.AccountType.VENDOR:
                if not d["retailer_id"]:
                    return Response({"error": "retailer_id_required_for_vendor"}, status=status.HTTP_400_BAD_REQUEST)
                retailer_obj = get_object_or_404(U, pk=d["retailer_id"])
                ret_prof = getattr(retailer_obj, "profile", None)
                if not ret_prof or ret_prof.account_type != AccountProfile.AccountType.RETAILER:
                    return Response({"error": "invalid_retailer"}, status=status.HTTP_400_BAD_REQUEST)

        roles = list(Role.objects.filter(id__in=d["role_ids"]))
        if any(r.name == "SUPER_ADMIN" for r in roles) and not request.user.is_superuser:
            return Response({"error": "cannot_create_super_admin"}, status=status.HTTP_403_FORBIDDEN)

        user = create_account_with_profile(
            created_by=request.user,
            username=d["username"],
            password=d["password"],
            account_type=target_type,
            email=d["email"],
            retailer_user=retailer_obj,
            entitlement_quota=d["entitlement_quota"],
            role_ids=d["role_ids"],
            full_name=d["full_name"],
            business_name=d["business_name"],
            contact_person=d["contact_person"],
            address=d["address"],
            mobile=d["mobile"],
            status_val=d["status"],
            request=request,
        )
        return Response(account_dict(user), status=status.HTTP_201_CREATED)


class AccountDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, account_id):
        target = get_object_or_404(get_user_model(), pk=account_id)
        if not can_view_account(request.user, target):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"account_view={account_id}", request=request)
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return Response(account_dict(target))

    def patch(self, request, account_id):
        if not user_has_perm(request.user, "accounts.manage"):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        target = get_object_or_404(get_user_model(), pk=account_id)
        if not can_manage_account(request.user, target):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"account_patch={account_id}", request=request)
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        if target.is_superuser and not request.user.is_superuser:
            return Response({"error": "cannot_modify_super_admin"}, status=status.HTTP_403_FORBIDDEN)
        s = AccountUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        tenant = getattr(target, "retailer_profile", None) or getattr(target, "vendor_profile", None)
        if tenant is not None:
            update_tenant_profile(tenant, d, "ACCOUNT_UPDATED", request=request)
        else:
            changed = []
            if "email" in d:
                target.email = d["email"]
                changed.append("email")
            if "status" in d:
                target.is_active = d["status"] == TenantStatus.ACTIVE
                changed.append("is_active")
            if changed:
                target.save(update_fields=changed)
            log_event(None, "ACCOUNT_UPDATED", f"user={target.username}", request=request)
        target.refresh_from_db()
        return Response(account_dict(target))

    def delete(self, request, account_id):
        if not user_has_perm(request.user, "accounts.manage"):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        target = get_object_or_404(get_user_model(), pk=account_id)
        if not can_manage_account(request.user, target):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"account_delete={account_id}", request=request)
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        if target.pk == request.user.pk or (target.is_superuser and not request.user.is_superuser):
            return Response({"error": "cannot_delete_account"}, status=status.HTTP_403_FORBIDDEN)
        deleted, msg = delete_or_disable_account(request.user, target, request=request)
        if deleted:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({"status": "disabled_with_history", "message": msg}, status=status.HTTP_200_OK)


class AccountStatusView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "accounts.manage"

    def post(self, request, account_id):
        target = get_object_or_404(get_user_model(), pk=account_id)
        if not can_manage_account(request.user, target):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"account_status={account_id}", request=request)
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        if target.is_superuser and not request.user.is_superuser:
            return Response({"error": "cannot_modify_super_admin"}, status=status.HTTP_403_FORBIDDEN)
        active = bool(request.data.get("is_active", True))
        set_account_active(request.user, target, active, request=request)
        return Response({"id": target.id, "username": target.username, "is_active": target.is_active})


class AccountActivateView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "accounts.manage"
    active_state = True

    def post(self, request, account_id):
        target = get_object_or_404(get_user_model(), pk=account_id)
        if not can_manage_account(request.user, target):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"account_activate={account_id}", request=request)
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        if target.is_superuser and not request.user.is_superuser:
            return Response({"error": "cannot_modify_super_admin"}, status=status.HTTP_403_FORBIDDEN)
        if not self.active_state and target.pk == request.user.pk:
            return Response({"error": "cannot_deactivate_self"}, status=status.HTTP_400_BAD_REQUEST)
        set_account_active(request.user, target, self.active_state, request=request)
        return Response(account_dict(target))


class AccountDeactivateView(AccountActivateView):
    active_state = False


class AccountQuotaView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "accounts.manage"

    def post(self, request, account_id):
        target = get_object_or_404(get_user_model(), pk=account_id)
        if not can_manage_account(request.user, target):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"account_quota={account_id}", request=request)
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        profile, _ = AccountProfile.objects.get_or_create(
            user=target,
            defaults={
                "account_type": AccountProfile.AccountType.SUPERUSER
                if target.is_superuser
                else AccountProfile.AccountType.RETAILER
            },
        )
        if "delta" in request.data and request.data.get("delta") not in ("", None):
            try:
                delta = int(request.data.get("delta"))
            except (TypeError, ValueError):
                return Response({"error": "invalid_delta"}, status=status.HTTP_400_BAD_REQUEST)
            base = profile.entitlement_quota if profile.entitlement_quota is not None else 0
            quota = max(0, base + delta)
        else:
            raw_quota = request.data.get("entitlement_quota", None)
            if raw_quota in ("", None):
                quota = None
            else:
                try:
                    quota = int(raw_quota)
                except (TypeError, ValueError):
                    return Response({"error": "invalid_quota"}, status=status.HTTP_400_BAD_REQUEST)
                if quota < 0:
                    return Response({"error": "invalid_quota"}, status=status.HTTP_400_BAD_REQUEST)
        profile.entitlement_quota = quota
        profile.save(update_fields=["entitlement_quota", "updated_at"])
        log_event(None, "ACCOUNT_LIMIT_UPDATED", f"user={target.username} limit={quota}", request=request)
        return Response({
            "id": target.id,
            "username": target.username,
            "entitlement_quota": profile.entitlement_quota,
            "entitlements_consumed": profile.entitlements_consumed,
        })


class RetailerListCreateView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "accounts.manage"

    def get(self, request):
        acct_type = get_account_type(request.user)
        if acct_type not in (AccountProfile.AccountType.SUPERUSER, AccountProfile.AccountType.RETAILER):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        qs = scope_retailers_queryset(request.user).select_related("account", "account__profile")
        return Response({"retailers": [retailer_dict(r) for r in qs]})

    def post(self, request):
        if not is_superuser_account(request.user):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", "retailer_create_non_superuser", request=request)
            return Response({"error": "superuser_required"}, status=status.HTTP_403_FORBIDDEN)
        s = TenantCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if get_user_model().objects.filter(username=d["username"]).exists():
            return Response({"error": "username_exists"}, status=status.HTTP_409_CONFLICT)
        user = create_account_with_profile(
            created_by=request.user,
            username=d["username"],
            password=d["password"],
            account_type=AccountProfile.AccountType.RETAILER,
            email=d["email"],
            entitlement_quota=d["entitlement_quota"],
            full_name=d["full_name"],
            business_name=d["business_name"],
            contact_person=d["contact_person"],
            address=d["address"],
            mobile=d["mobile"],
            status_val=d["status"],
            request=request,
        )
        return Response(retailer_dict(user.retailer_profile), status=status.HTTP_201_CREATED)


class RetailerDetailView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "accounts.manage"

    def get(self, request, retailer_id):
        retailer = get_object_or_404(Retailer.objects.select_related("account", "account__profile"), pk=retailer_id)
        if not can_access_retailer(request.user, retailer):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"retailer_view={retailer_id}", request=request)
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return Response(retailer_dict(retailer))

    def patch(self, request, retailer_id):
        if not is_superuser_account(request.user):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"retailer_patch={retailer_id}", request=request)
            return Response({"error": "superuser_required"}, status=status.HTTP_403_FORBIDDEN)
        retailer = get_object_or_404(Retailer.objects.select_related("account", "account__profile"), pk=retailer_id)
        s = TenantUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        update_tenant_profile(retailer, s.validated_data, "RETAILER_UPDATED", request=request)
        retailer.refresh_from_db()
        return Response(retailer_dict(retailer))

    def delete(self, request, retailer_id):
        if not is_superuser_account(request.user):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"retailer_delete={retailer_id}", request=request)
            return Response({"error": "superuser_required"}, status=status.HTTP_403_FORBIDDEN)
        retailer = get_object_or_404(Retailer.objects.select_related("account"), pk=retailer_id)
        if retailer.account_id == request.user.pk:
            return Response({"error": "cannot_delete_self"}, status=status.HTTP_403_FORBIDDEN)
        deleted, msg = delete_or_disable_account(request.user, retailer.account, request=request)
        if deleted:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({"status": "disabled_with_history", "message": msg}, status=status.HTTP_200_OK)


class VendorListCreateView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "accounts.manage"

    def get(self, request):
        qs = scope_vendors_queryset(request.user).select_related(
            "account", "account__profile", "retailer", "retailer__account"
        )
        return Response({"vendors": [vendor_dict(v) for v in qs]})

    def post(self, request):
        s = VendorCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        U = get_user_model()
        if U.objects.filter(username=d["username"]).exists():
            return Response({"error": "username_exists"}, status=status.HTTP_409_CONFLICT)

        actor_type = get_account_type(request.user)
        if actor_type == AccountProfile.AccountType.RETAILER:
            if d["retailer_id"] is not None and d["retailer_id"] != request.user.id:
                log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", "vendor_create_other_retailer", request=request)
                return Response({"error": "cannot_assign_other_retailer"}, status=status.HTTP_403_FORBIDDEN)
            if d["retailer_profile_id"] is not None:
                own_rp = getattr(request.user, "retailer_profile", None)
                if not own_rp or str(own_rp.id) != str(d["retailer_profile_id"]):
                    log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", "vendor_create_other_retailer_profile", request=request)
                    return Response({"error": "cannot_assign_other_retailer"}, status=status.HTTP_403_FORBIDDEN)
            retailer_user = request.user
        elif actor_type == AccountProfile.AccountType.SUPERUSER:
            if d["retailer_profile_id"] is not None:
                ret_rec = get_object_or_404(Retailer, pk=d["retailer_profile_id"])
                retailer_user = ret_rec.account
            elif d["retailer_id"] is not None:
                retailer_user = get_object_or_404(U, pk=d["retailer_id"])
                ret_prof = getattr(retailer_user, "profile", None)
                if not ret_prof or ret_prof.account_type != AccountProfile.AccountType.RETAILER:
                    return Response({"error": "invalid_retailer"}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({"error": "retailer_id_required"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", "vendor_create_forbidden", request=request)
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

        user = create_account_with_profile(
            created_by=request.user,
            username=d["username"],
            password=d["password"],
            account_type=AccountProfile.AccountType.VENDOR,
            email=d["email"],
            retailer_user=retailer_user,
            entitlement_quota=d["entitlement_quota"],
            full_name=d["full_name"],
            business_name=d["business_name"],
            contact_person=d["contact_person"],
            address=d["address"],
            mobile=d["mobile"],
            status_val=d["status"],
            request=request,
        )
        return Response(vendor_dict(user.vendor_profile), status=status.HTTP_201_CREATED)


class VendorDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, vendor_id):
        vendor = get_object_or_404(
            Vendor.objects.select_related("account", "account__profile", "retailer"), pk=vendor_id
        )
        if not can_access_vendor(request.user, vendor):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"vendor_view={vendor_id}", request=request)
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return Response(vendor_dict(vendor))

    def patch(self, request, vendor_id):
        if not user_has_perm(request.user, "accounts.manage"):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        vendor = get_object_or_404(
            Vendor.objects.select_related("account", "account__profile", "retailer"), pk=vendor_id
        )
        if not can_access_vendor(request.user, vendor):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"vendor_patch={vendor_id}", request=request)
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        s = TenantUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        update_tenant_profile(vendor, s.validated_data, "VENDOR_UPDATED", request=request)
        vendor.refresh_from_db()
        return Response(vendor_dict(vendor))

    def delete(self, request, vendor_id):
        if not user_has_perm(request.user, "accounts.manage"):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        vendor = get_object_or_404(
            Vendor.objects.select_related("account", "retailer"), pk=vendor_id
        )
        if not can_access_vendor(request.user, vendor):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"vendor_delete={vendor_id}", request=request)
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        deleted, msg = delete_or_disable_account(request.user, vendor.account, request=request)
        if deleted:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({"status": "disabled_with_history", "message": msg}, status=status.HTTP_200_OK)
