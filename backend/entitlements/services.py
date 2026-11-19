"""Atomic entitlement ledger services: allocation, transfer, expiry, and consumption."""
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import AccountProfile, consume_entitlement
from audit.models import log_event
from devices.ownership import get_account_type
from entitlements.models import EntitlementAllocation, EntitlementConsumption, EntitlementTransfer


def expire_stale_allocations(now=None) -> int:
    now = now or timezone.now()
    return EntitlementAllocation.objects.filter(
        status=EntitlementAllocation.Status.ACTIVE,
        expires_at__lte=now,
    ).update(status=EntitlementAllocation.Status.EXPIRED, updated_at=now)


def get_account_balance(user) -> dict:
    expire_stale_allocations()
    now = timezone.now()
    qs = EntitlementAllocation.objects.filter(allocated_to=user).exclude(
        status=EntitlementAllocation.Status.CANCELLED
    )
    if not qs.exists():
        prof = AccountProfile.objects.filter(user=user).first()
        if prof and prof.entitlement_quota is not None:
            avail = 0 if not user.is_active else max(0, prof.entitlement_quota - prof.entitlements_consumed)
            return {
                "allocated": prof.entitlement_quota,
                "distributed": 0,
                "consumed": prof.entitlements_consumed,
                "available": avail,
                "expired": 0,
                "disabled": 0 if user.is_active else max(0, prof.entitlement_quota - prof.entitlements_consumed),
            }
        return {
            "allocated": 0,
            "distributed": 0,
            "consumed": prof.entitlements_consumed if prof else 0,
            "available": 0 if not user.is_active else (None if (prof and prof.entitlement_quota is None) else 0),
            "expired": 0,
            "disabled": 0,
        }

    agg = qs.aggregate(
        allocated=Sum("allocated_quantity"),
        distributed=Sum("distributed_quantity"),
        consumed=Sum("consumed_quantity"),
    )
    active_avail = (
        qs.filter(status=EntitlementAllocation.Status.ACTIVE, expires_at__gt=now)
        .aggregate(v=Sum("available_quantity"))["v"]
        or 0
    ) if user.is_active else 0
    expired_avail = (
        qs.filter(expires_at__lte=now).aggregate(v=Sum("available_quantity"))["v"] or 0
    )
    disabled_avail = (
        qs.filter(status=EntitlementAllocation.Status.DISABLED).aggregate(v=Sum("available_quantity"))["v"] or 0
    )
    return {
        "allocated": agg["allocated"] or 0,
        "distributed": agg["distributed"] or 0,
        "consumed": agg["consumed"] or 0,
        "available": active_avail,
        "expired": expired_avail,
        "disabled": disabled_avail,
    }


def disable_account_entitlements(user, actor=None, request=None) -> int:
    """Disables ONLY this account's own unconsumed entitlements; never touches child vendors' allocations."""
    from devices.models import EnrollmentSession

    now = timezone.now()
    updated = EntitlementAllocation.objects.filter(
        allocated_to=user,
        status=EntitlementAllocation.Status.ACTIVE,
    ).update(status=EntitlementAllocation.Status.DISABLED, updated_at=now)

    # Revoke pending enrollment sessions owned by this user directly (leave other vendors' sessions intact)
    EnrollmentSession.objects.filter(
        created_by=user,
        status=EnrollmentSession.Status.PENDING,
    ).update(status=EnrollmentSession.Status.REVOKED, token_encrypted="")

    prof = AccountProfile.objects.filter(user=user).first()
    if prof and prof.entitlement_quota is not None:
        # Keep quota capped at consumed so legacy fallback cannot bypass disabled state
        prof.entitlement_quota = prof.entitlements_consumed
        prof.save(update_fields=["entitlement_quota", "updated_at"])

    if updated:
        log_event(
            None,
            "ENTITLEMENTS_DISABLED",
            f"user={user.username} allocations_disabled={updated}",
            actor=actor,
            request=request,
        )
    return updated


def has_available_entitlement(user) -> bool:
    if not user:
        return True
    if not getattr(user, "is_active", False):
        return False
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return True
    expire_stale_allocations()
    now = timezone.now()
    if EntitlementAllocation.objects.filter(allocated_to=user).exists():
        return EntitlementAllocation.objects.filter(
            allocated_to=user,
            status=EntitlementAllocation.Status.ACTIVE,
            expires_at__gt=now,
            available_quantity__gt=0,
        ).exists()
    prof = AccountProfile.objects.filter(user=user).first()
    if prof and prof.entitlement_quota is not None:
        return prof.entitlements_consumed < prof.entitlement_quota
    return True


def _sync_profile_quota(user):
    prof = AccountProfile.objects.filter(user=user).first()
    if prof is None:
        return
    bal = get_account_balance(user)
    if bal["available"] is not None:
        prof.entitlement_quota = bal["allocated"] - bal["distributed"]
        prof.entitlements_consumed = bal["consumed"]
        prof.save(update_fields=["entitlement_quota", "entitlements_consumed", "updated_at"])


@transaction.atomic
def allocate_entitlement(actor, recipient, quantity: int, notes: str = "", request=None) -> list[EntitlementAllocation]:
    if quantity < 1:
        raise ValidationError({"error": "quantity_must_be_positive"})
    if not recipient.is_active:
        raise ValidationError({"error": "recipient_inactive"})

    actor_type = get_account_type(actor)
    recipient_type = get_account_type(recipient)
    if recipient_type not in (AccountProfile.AccountType.RETAILER, AccountProfile.AccountType.VENDOR):
        raise ValidationError({"error": "invalid_recipient_account_type"})

    expire_stale_allocations()
    now = timezone.now()
    created: list[EntitlementAllocation] = []

    if actor_type == AccountProfile.AccountType.SUPERUSER:
        alloc = EntitlementAllocation.objects.create(
            allocated_to=recipient,
            allocated_by=actor,
            allocated_quantity=quantity,
            available_quantity=quantity,
            issued_at=now,
            expires_at=now + timedelta(days=365),
            status=EntitlementAllocation.Status.ACTIVE,
            notes=notes[:255],
        )
        created.append(alloc)
    elif actor_type == AccountProfile.AccountType.RETAILER:
        rec_prof = AccountProfile.objects.filter(user=recipient).first()
        if (
            recipient_type != AccountProfile.AccountType.VENDOR
            or not rec_prof
            or rec_prof.retailer_id != actor.id
        ):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"allocate_to={recipient.id}", actor=actor, request=request)
            raise PermissionDenied("Retailer can only allocate entitlements to its own active vendors.")

        sources = list(
            EntitlementAllocation.objects.select_for_update()
            .filter(
                allocated_to=actor,
                status=EntitlementAllocation.Status.ACTIVE,
                expires_at__gt=now,
                available_quantity__gt=0,
            )
            .order_by("expires_at", "issued_at")
        )
        total_avail = sum(s.available_quantity for s in sources)
        if total_avail < quantity:
            raise ValidationError({"error": "insufficient_entitlement_balance"})

        remaining = quantity
        for src in sources:
            if remaining == 0:
                break
            take = min(src.available_quantity, remaining)
            src.distributed_quantity += take
            src.available_quantity -= take
            src.status = src.compute_status(now)
            src.save(update_fields=["distributed_quantity", "available_quantity", "status", "updated_at"])

            child = EntitlementAllocation.objects.create(
                allocated_to=recipient,
                allocated_by=actor,
                parent_allocation=src,
                allocated_quantity=take,
                available_quantity=take,
                issued_at=now,
                expires_at=src.expires_at,
                status=EntitlementAllocation.Status.ACTIVE,
                notes=notes[:255],
            )
            created.append(child)
            remaining -= take
        _sync_profile_quota(actor)
    else:
        log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", "vendor_allocate_forbidden", actor=actor, request=request)
        raise PermissionDenied("Vendors cannot allocate entitlements.")

    _sync_profile_quota(recipient)
    log_event(
        None,
        "ENTITLEMENT_ALLOCATED",
        f"to={recipient.username} qty={quantity}",
        actor=actor,
        request=request,
    )
    return created


@transaction.atomic
def transfer_entitlement(
    actor, sender, receiver, quantity: int, reason: str = "", request=None
) -> list[EntitlementTransfer]:
    if quantity < 1:
        raise ValidationError({"error": "quantity_must_be_positive"})
    if sender.pk == receiver.pk:
        raise ValidationError({"error": "cannot_transfer_to_self"})
    if not sender.is_active or not receiver.is_active:
        raise ValidationError({"error": "inactive_account"})

    actor_type = get_account_type(actor)
    sender_type = get_account_type(sender)
    receiver_type = get_account_type(receiver)

    if sender_type != AccountProfile.AccountType.VENDOR or receiver_type != AccountProfile.AccountType.VENDOR:
        raise ValidationError({"error": "transfers_only_between_vendors"})

    s_prof = AccountProfile.objects.filter(user=sender).first()
    r_prof = AccountProfile.objects.filter(user=receiver).first()
    if not s_prof or not r_prof or s_prof.retailer_id != r_prof.retailer_id:
        log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", "cross_retailer_entitlement_transfer", actor=actor, request=request)
        raise PermissionDenied("Cross-retailer entitlement transfers are prohibited.")

    if actor_type == AccountProfile.AccountType.VENDOR:
        if actor.pk != sender.pk:
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", "transfer_from_other_vendor", actor=actor, request=request)
            raise PermissionDenied("Vendor can only transfer its own unused entitlements.")
    elif actor_type == AccountProfile.AccountType.RETAILER:
        if s_prof.retailer_id != actor.pk:
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", "retailer_transfer_other_hierarchy", actor=actor, request=request)
            raise PermissionDenied("Retailer can only transfer entitlements within its own vendors.")
    elif actor_type != AccountProfile.AccountType.SUPERUSER:
        raise PermissionDenied("Forbidden")

    expire_stale_allocations()
    now = timezone.now()
    sources = list(
        EntitlementAllocation.objects.select_for_update()
        .filter(
            allocated_to=sender,
            status=EntitlementAllocation.Status.ACTIVE,
            expires_at__gt=now,
            available_quantity__gt=0,
        )
        .order_by("expires_at", "issued_at")
    )
    total_avail = sum(s.available_quantity for s in sources)
    if total_avail < quantity:
        raise ValidationError({"error": "insufficient_unused_entitlements"})

    transfers: list[EntitlementTransfer] = []
    remaining = quantity
    for src in sources:
        if remaining == 0:
            break
        take = min(src.available_quantity, remaining)
        src.distributed_quantity += take
        src.available_quantity -= take
        src.status = src.compute_status(now)
        src.save(update_fields=["distributed_quantity", "available_quantity", "status", "updated_at"])

        target_alloc = EntitlementAllocation.objects.create(
            allocated_to=receiver,
            allocated_by=actor,
            parent_allocation=src.parent_allocation,
            allocated_quantity=take,
            available_quantity=take,
            issued_at=now,
            expires_at=src.expires_at,
            status=EntitlementAllocation.Status.ACTIVE,
            notes=f"Transfer from {sender.username}: {reason[:180]}",
        )
        tr = EntitlementTransfer.objects.create(
            sender=sender,
            receiver=receiver,
            source_allocation=src,
            target_allocation=target_alloc,
            quantity=take,
            transferred_by=actor,
            reason=reason[:300],
            status=EntitlementTransfer.Status.COMPLETED,
        )
        transfers.append(tr)
        remaining -= take

    _sync_profile_quota(sender)
    _sync_profile_quota(receiver)
    log_event(
        None,
        "ENTITLEMENT_TRANSFERRED",
        f"from={sender.username} to={receiver.username} qty={quantity}",
        actor=actor,
        request=request,
    )
    return transfers


@transaction.atomic
def consume_entitlement_for_device(user, device, registration_reference: str = "", request=None) -> bool:
    """Atomically consumes exactly one active, non-expired entitlement upon device registration commit."""
    if not user:
        return True
    acct_type = get_account_type(user)
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return True

    expire_stale_allocations()
    now = timezone.now()
    if EntitlementAllocation.objects.filter(allocated_to=user).exists():
        alloc = (
            EntitlementAllocation.objects.select_for_update()
            .filter(
                allocated_to=user,
                status=EntitlementAllocation.Status.ACTIVE,
                expires_at__gt=now,
                available_quantity__gt=0,
            )
            .order_by("expires_at", "issued_at")
            .first()
        )
        if alloc is None:
            return False
        alloc.consumed_quantity += 1
        alloc.available_quantity -= 1
        alloc.status = alloc.compute_status(now)
        alloc.save(update_fields=["consumed_quantity", "available_quantity", "status", "updated_at"])

        ref = registration_reference or f"REG-{str(device.id)[:8].upper()}"
        EntitlementConsumption.objects.create(
            allocation=alloc,
            device=device,
            retailer=device.retailer,
            vendor=device.vendor,
            registration_reference=ref,
        )
        _sync_profile_quota(user)
        log_event(device, "ENTITLEMENT_CONSUMED", f"alloc={alloc.id} ref={ref}", actor=user, request=request)
        return True

    # Legacy fallback for accounts without explicit EntitlementAllocation rows
    return consume_entitlement(user)
