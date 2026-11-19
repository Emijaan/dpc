"""Service layer for three-level account hierarchy (Superuser -> Retailer -> Vendor)."""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import ProtectedError, Q

from accounts.models import AccountProfile, Retailer, TenantStatus, Vendor
from audit.models import log_event
from roles.models import AccountRole, Role
from roles.permissions import ensure_default_rbac


def _ensure_retailer_record(retailer_user) -> Retailer:
    rec = getattr(retailer_user, "retailer_profile", None)
    if rec is not None:
        return rec
    rec, _ = Retailer.objects.get_or_create(
        account=retailer_user,
        defaults={
            "full_name": retailer_user.get_full_name() or retailer_user.username,
            "business_name": retailer_user.username,
            "email": retailer_user.email or "",
            "status": TenantStatus.ACTIVE if retailer_user.is_active else TenantStatus.INACTIVE,
        },
    )
    return rec


@transaction.atomic
def create_account_with_profile(
    *,
    created_by,
    username: str,
    password: str,
    account_type: str,
    email: str = "",
    retailer_user=None,
    entitlement_quota: int | None = None,
    role_ids: list[int] | None = None,
    full_name: str = "",
    business_name: str = "",
    contact_person: str = "",
    address: str = "",
    mobile: str = "",
    status_val: str = TenantStatus.ACTIVE,
    request=None,
):
    ensure_default_rbac()
    U = get_user_model()
    is_active = status_val == TenantStatus.ACTIVE
    user = U.objects.create_user(
        username=username,
        email=email,
        password=password,
        is_staff=True,
        is_active=is_active,
        is_superuser=(account_type == AccountProfile.AccountType.SUPERUSER and created_by.is_superuser),
    )
    AccountProfile.objects.create(
        user=user,
        account_type=account_type,
        retailer=retailer_user if account_type == AccountProfile.AccountType.VENDOR else None,
        entitlement_quota=entitlement_quota,
    )

    if account_type == AccountProfile.AccountType.RETAILER:
        Retailer.objects.create(
            account=user,
            full_name=full_name or username,
            business_name=business_name or full_name or username,
            contact_person=contact_person or full_name or username,
            address=address,
            mobile=mobile,
            email=email,
            status=status_val,
        )
    elif account_type == AccountProfile.AccountType.VENDOR:
        ret_rec = _ensure_retailer_record(retailer_user)
        Vendor.objects.create(
            account=user,
            retailer=ret_rec,
            full_name=full_name or username,
            business_name=business_name or full_name or username,
            contact_person=contact_person or full_name or username,
            address=address,
            mobile=mobile,
            email=email,
            status=status_val,
        )

    roles = list(Role.objects.filter(id__in=(role_ids or [])))
    if not roles and account_type in (AccountProfile.AccountType.RETAILER, AccountProfile.AccountType.VENDOR):
        default_role = Role.objects.filter(name=account_type).first()
        if default_role:
            roles = [default_role]
    for r in roles:
        AccountRole.objects.create(user=user, role=r, assigned_by=created_by)

    if entitlement_quota and entitlement_quota > 0 and account_type in (
        AccountProfile.AccountType.RETAILER,
        AccountProfile.AccountType.VENDOR,
    ):
        from entitlements.models import EntitlementAllocation
        from entitlements.services import allocate_entitlement

        if getattr(created_by, "is_superuser", False) or EntitlementAllocation.objects.filter(
            allocated_to=created_by
        ).exists():
            allocate_entitlement(
                created_by,
                user,
                entitlement_quota,
                notes="Initial account allocation",
                request=request,
            )

    log_event(None, "ACCOUNT_CREATED", f"user={user.username} type={account_type}", request=request)
    return user


@transaction.atomic
def set_account_active(actor, target, active: bool, request=None):
    target.is_active = active
    target.save(update_fields=["is_active"])
    new_status = TenantStatus.ACTIVE if active else TenantStatus.INACTIVE
    if hasattr(target, "retailer_profile"):
        target.retailer_profile.status = new_status
        target.retailer_profile.save(update_fields=["status", "updated_at"])
    if hasattr(target, "vendor_profile"):
        target.vendor_profile.status = new_status
        target.vendor_profile.save(update_fields=["status", "updated_at"])
    if not active:
        from entitlements.services import disable_account_entitlements

        disable_account_entitlements(target, actor=actor, request=request)
    event = "ACCOUNT_ACTIVATED" if active else "ACCOUNT_DEACTIVATED"
    log_event(None, event, f"user={target.username} active={active}", actor=actor, request=request)
    return target


@transaction.atomic
def delete_or_disable_account(actor, target, request=None) -> tuple[bool, str]:
    """
    Disables the account's own unconsumed entitlements (leaving child vendors' allocations intact).
    Hard-deletes the account if it has no protected devices, customers, child vendors, or consumptions;
    otherwise keeps historical records intact and leaves the account deactivated.
    """
    from devices.models import Customer, Device, EnrollmentSession
    from entitlements.models import EntitlementAllocation, EntitlementConsumption, EntitlementTransfer
    from entitlements.services import disable_account_entitlements

    disable_account_entitlements(target, actor=actor, request=request)
    uname = target.username

    has_devices = Device.objects.filter(
        Q(retailer=target) | Q(vendor=target) | Q(original_retailer=target) | Q(original_vendor=target) | Q(registered_by_account=target)
    ).exists()
    has_customers = Customer.objects.filter(
        Q(retailer=target) | Q(vendor=target) | Q(registered_by_account=target)
    ).exists()
    has_vendors = hasattr(target, "retailer_profile") and target.retailer_profile.vendors.exists()
    has_consumptions = EntitlementConsumption.objects.filter(
        Q(retailer=target) | Q(vendor=target) | Q(allocation__allocated_to=target) | Q(allocation__allocated_by=target)
    ).exists()
    has_child_allocs = EntitlementAllocation.objects.filter(
        allocated_by=target
    ).exclude(allocated_to=target).exists()

    if has_devices or has_customers or has_vendors or has_consumptions or has_child_allocs:
        set_account_active(actor, target, False, request=request)
        return (
            False,
            f"Account '{uname}' and its unallocated entitlements have been disabled; existing vendor allocations and device history are preserved.",
        )

    try:
        with transaction.atomic():
            EnrollmentSession.objects.filter(
                Q(created_by=target) | Q(vendor=target) | Q(retailer=target),
                registered_device__isnull=True,
            ).delete()
            EntitlementTransfer.objects.filter(
                Q(sender=target) | Q(receiver=target) | Q(transferred_by=target)
            ).delete()
            EntitlementAllocation.objects.filter(
                Q(allocated_to=target) | Q(allocated_by=target)
            ).delete()
            target.delete()
        log_event(None, "ACCOUNT_DELETED", f"user={uname}", actor=actor, request=request)
        return True, f"Deleted account '{uname}'."
    except ProtectedError:
        set_account_active(actor, target, False, request=request)
        return (
            False,
            f"Account '{uname}' and its unallocated entitlements have been disabled; historical records are preserved.",
        )


@transaction.atomic
def update_tenant_profile(profile_obj, data: dict, event_name: str, request=None):
    editable = ("full_name", "business_name", "contact_person", "address", "mobile", "email", "status")
    changed = []
    for f in editable:
        if f in data:
            setattr(profile_obj, f, data[f])
            changed.append(f)
    if changed:
        changed.append("updated_at")
        profile_obj.save(update_fields=changed)
    user = profile_obj.account
    user_changed = []
    if "email" in data and user.email != data["email"]:
        user.email = data["email"]
        user_changed.append("email")
    if "status" in data:
        want_active = data["status"] == TenantStatus.ACTIVE
        if user.is_active != want_active:
            user.is_active = want_active
            user_changed.append("is_active")
            if not want_active:
                from entitlements.services import disable_account_entitlements

                disable_account_entitlements(user, request=request)
    if user_changed:
        user.save(update_fields=user_changed)
    log_event(None, event_name, f"account={user.username} fields={changed}", request=request)
    return profile_obj
