"""Centralized backend ownership and tenant-isolation authorization."""
from django.contrib.auth import get_user_model
from django.db.models import Q

from accounts.models import AccountProfile, Retailer, Vendor
from audit.models import DeviceAuditLog
from commands.models import DeviceCommand
from devices.models import Customer, Device, EnrollmentSession


def is_active_user(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and getattr(user, "is_active", False))


def get_account_type(user) -> str | None:
    if not is_active_user(user):
        return None
    if getattr(user, "is_superuser", False):
        return AccountProfile.AccountType.SUPERUSER
    profile = AccountProfile.objects.filter(user=user).first()
    if profile is not None:
        return profile.account_type
    if getattr(user, "is_staff", False):
        return AccountProfile.AccountType.SUPERUSER
    return None


def is_superuser_account(user) -> bool:
    return get_account_type(user) == AccountProfile.AccountType.SUPERUSER


def get_ownership_context_for_creator(user) -> tuple:
    """Returns (superuser, retailer, vendor) for a user creating a customer/enrollment."""
    User = get_user_model()
    platform_su = User.objects.filter(is_superuser=True, is_active=True).order_by("id").first()
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return user, None, None
    if acct_type == AccountProfile.AccountType.RETAILER:
        return platform_su, user, None
    if acct_type == AccountProfile.AccountType.VENDOR:
        profile = AccountProfile.objects.select_related("retailer").filter(user=user).first()
        retailer = profile.retailer if profile else None
        return platform_su, retailer, user
    return platform_su, None, None


def scope_devices_queryset(user, qs=None):
    base = qs if qs is not None else Device.objects.all()
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return base
    if acct_type == AccountProfile.AccountType.RETAILER:
        return base.filter(retailer=user)
    if acct_type == AccountProfile.AccountType.VENDOR:
        return base.filter(vendor=user)
    return base.none()


def can_access_device(user, device: Device) -> bool:
    if not is_active_user(user) or device is None:
        return False
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return True
    if acct_type == AccountProfile.AccountType.RETAILER:
        return device.retailer_id == user.id
    if acct_type == AccountProfile.AccountType.VENDOR:
        return device.vendor_id == user.id
    return False


def scope_customers_queryset(user, qs=None):
    base = qs if qs is not None else Customer.objects.all()
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return base
    if acct_type == AccountProfile.AccountType.RETAILER:
        return base.filter(retailer=user)
    if acct_type == AccountProfile.AccountType.VENDOR:
        return base.filter(vendor=user)
    return base.none()


def can_access_customer(user, customer: Customer) -> bool:
    if not is_active_user(user) or customer is None:
        return False
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return True
    if acct_type == AccountProfile.AccountType.RETAILER:
        return customer.retailer_id == user.id
    if acct_type == AccountProfile.AccountType.VENDOR:
        return customer.vendor_id == user.id
    return False


def scope_enrollments_queryset(user, qs=None):
    base = qs if qs is not None else EnrollmentSession.objects.all()
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return base
    if acct_type == AccountProfile.AccountType.RETAILER:
        return base.filter(retailer=user)
    if acct_type == AccountProfile.AccountType.VENDOR:
        return base.filter(vendor=user)
    return base.none()


def can_access_enrollment(user, session: EnrollmentSession) -> bool:
    if not is_active_user(user) or session is None:
        return False
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return True
    if acct_type == AccountProfile.AccountType.RETAILER:
        return session.retailer_id == user.id
    if acct_type == AccountProfile.AccountType.VENDOR:
        return session.vendor_id == user.id
    return False


def scope_commands_queryset(user, qs=None):
    base = qs if qs is not None else DeviceCommand.objects.all()
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return base
    if acct_type == AccountProfile.AccountType.RETAILER:
        return base.filter(device__retailer=user)
    if acct_type == AccountProfile.AccountType.VENDOR:
        return base.filter(device__vendor=user)
    return base.none()


def scope_audit_logs_queryset(user, qs=None):
    base = qs if qs is not None else DeviceAuditLog.objects.all()
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return base
    if acct_type == AccountProfile.AccountType.RETAILER:
        return base.filter(Q(device__retailer=user) | Q(actor=user) | Q(actor__profile__retailer=user))
    if acct_type == AccountProfile.AccountType.VENDOR:
        return base.filter(Q(device__vendor=user) | Q(actor=user))
    return base.none()


def scope_accounts_queryset(user, qs=None):
    User = get_user_model()
    base = qs if qs is not None else User.objects.all()
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return base
    if acct_type == AccountProfile.AccountType.RETAILER:
        return base.filter(Q(pk=user.pk) | Q(profile__retailer=user))
    if acct_type == AccountProfile.AccountType.VENDOR:
        return base.filter(pk=user.pk)
    return base.none()


def can_manage_account(actor, target) -> bool:
    if not is_active_user(actor) or target is None:
        return False
    acct_type = get_account_type(actor)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return True
    if acct_type == AccountProfile.AccountType.RETAILER:
        if target.pk == actor.pk:
            return True
        target_profile = AccountProfile.objects.filter(user=target).first()
        return bool(
            target_profile
            and target_profile.account_type == AccountProfile.AccountType.VENDOR
            and target_profile.retailer_id == actor.pk
        )
    return False


def can_view_account(actor, target) -> bool:
    if not is_active_user(actor) or target is None:
        return False
    if target.pk == actor.pk:
        return True
    return can_manage_account(actor, target)


def scope_retailers_queryset(user, qs=None):
    base = qs if qs is not None else Retailer.objects.all()
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return base
    if acct_type == AccountProfile.AccountType.RETAILER:
        return base.filter(account=user)
    return base.none()


def can_access_retailer(user, retailer: Retailer) -> bool:
    if not is_active_user(user) or retailer is None:
        return False
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return True
    if acct_type == AccountProfile.AccountType.RETAILER:
        return retailer.account_id == user.id
    return False


def scope_vendors_queryset(user, qs=None):
    base = qs if qs is not None else Vendor.objects.all()
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return base
    if acct_type == AccountProfile.AccountType.RETAILER:
        return base.filter(retailer__account=user)
    if acct_type == AccountProfile.AccountType.VENDOR:
        return base.filter(account=user)
    return base.none()


def can_access_vendor(user, vendor: Vendor) -> bool:
    if not is_active_user(user) or vendor is None:
        return False
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return True
    if acct_type == AccountProfile.AccountType.RETAILER:
        return vendor.retailer.account_id == user.id
    if acct_type == AccountProfile.AccountType.VENDOR:
        return vendor.account_id == user.id
    return False
