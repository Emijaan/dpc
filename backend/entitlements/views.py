from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import AccountProfile
from devices.ownership import can_manage_account, get_account_type, scope_accounts_queryset
from entitlements.models import EntitlementAllocation, EntitlementConsumption, EntitlementTransfer
from entitlements.services import (
    allocate_entitlement,
    expire_stale_allocations,
    get_account_balance,
    transfer_entitlement,
)
from roles.permissions import ensure_default_rbac


def allocation_dict(a: EntitlementAllocation) -> dict:
    return {
        "id": str(a.id),
        "allocated_to_id": a.allocated_to_id,
        "allocated_to_username": a.allocated_to.username,
        "allocated_by_id": a.allocated_by_id,
        "allocated_by_username": a.allocated_by.username,
        "parent_allocation_id": str(a.parent_allocation_id) if a.parent_allocation_id else None,
        "allocated_quantity": a.allocated_quantity,
        "distributed_quantity": a.distributed_quantity,
        "consumed_quantity": a.consumed_quantity,
        "available_quantity": a.available_quantity,
        "issued_at": a.issued_at.isoformat(),
        "expires_at": a.expires_at.isoformat(),
        "status": a.status,
        "notes": a.notes,
    }


def transfer_dict(t: EntitlementTransfer) -> dict:
    return {
        "id": str(t.id),
        "sender_id": t.sender_id,
        "sender_username": t.sender.username,
        "receiver_id": t.receiver_id,
        "receiver_username": t.receiver.username,
        "quantity": t.quantity,
        "transferred_by_id": t.transferred_by_id,
        "transferred_by_username": t.transferred_by.username,
        "transfer_date": t.transfer_date.isoformat(),
        "reason": t.reason,
        "status": t.status,
    }


def consumption_dict(c: EntitlementConsumption) -> dict:
    return {
        "id": str(c.id),
        "allocation_id": str(c.allocation_id),
        "device_id": str(c.device_id),
        "device_identifier": c.device.device_identifier,
        "retailer_id": c.retailer_id,
        "vendor_id": c.vendor_id,
        "registration_reference": c.registration_reference,
        "consumed_at": c.consumed_at.isoformat(),
    }


def _scope_allocations(user):
    acct_type = get_account_type(user)
    base = EntitlementAllocation.objects.select_related("allocated_to", "allocated_by")
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return base
    if acct_type == AccountProfile.AccountType.RETAILER:
        return base.filter(Q(allocated_to=user) | Q(allocated_to__profile__retailer=user))
    if acct_type == AccountProfile.AccountType.VENDOR:
        return base.filter(allocated_to=user)
    return base.none()


def _scope_transfers(user):
    acct_type = get_account_type(user)
    base = EntitlementTransfer.objects.select_related("sender", "receiver", "transferred_by")
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return base
    if acct_type == AccountProfile.AccountType.RETAILER:
        return base.filter(Q(sender__profile__retailer=user) | Q(receiver__profile__retailer=user))
    if acct_type == AccountProfile.AccountType.VENDOR:
        return base.filter(Q(sender=user) | Q(receiver=user))
    return base.none()


def _scope_consumptions(user):
    acct_type = get_account_type(user)
    base = EntitlementConsumption.objects.select_related("device", "allocation")
    if acct_type == AccountProfile.AccountType.SUPERUSER:
        return base
    if acct_type == AccountProfile.AccountType.RETAILER:
        return base.filter(retailer=user)
    if acct_type == AccountProfile.AccountType.VENDOR:
        return base.filter(vendor=user)
    return base.none()


class AllocateSerializer(serializers.Serializer):
    recipient_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=100000)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class TransferSerializer(serializers.Serializer):
    sender_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    receiver_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=100000)
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class EntitlementAllocateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ensure_default_rbac()
        s = AllocateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        recipient = get_object_or_404(get_user_model(), pk=d["recipient_id"])
        created = allocate_entitlement(request.user, recipient, d["quantity"], notes=d["notes"], request=request)
        return Response(
            {
                "allocations": [allocation_dict(a) for a in created],
                "recipient_balance": get_account_balance(recipient),
            },
            status=status.HTTP_201_CREATED,
        )


class EntitlementTransferView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = TransferSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        U = get_user_model()
        sender = get_object_or_404(U, pk=d["sender_id"]) if d["sender_id"] else request.user
        receiver = get_object_or_404(U, pk=d["receiver_id"])
        transfers = transfer_entitlement(
            request.user, sender, receiver, d["quantity"], reason=d["reason"], request=request
        )
        return Response(
            {
                "transfers": [transfer_dict(t) for t in transfers],
                "sender_balance": get_account_balance(sender),
                "receiver_balance": get_account_balance(receiver),
            },
            status=status.HTTP_201_CREATED,
        )


class EntitlementListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        expire_stale_allocations()
        qs = _scope_allocations(request.user)
        return Response({"allocations": [allocation_dict(a) for a in qs[:200]]})


class EntitlementBalanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        target_id = request.GET.get("account_id")
        if target_id:
            target = get_object_or_404(get_user_model(), pk=target_id)
            if target.pk != request.user.pk and not can_manage_account(request.user, target):
                return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        else:
            target = request.user
        bal = get_account_balance(target)
        return Response({"account_id": target.id, "username": target.username, **bal})


class EntitlementHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        expire_stale_allocations()
        allocs = [allocation_dict(a) for a in _scope_allocations(request.user)[:100]]
        transfers = [transfer_dict(t) for t in _scope_transfers(request.user)[:100]]
        return Response({"allocations": allocs, "transfers": transfers})


class EntitlementConsumptionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = _scope_consumptions(request.user)
        return Response({"consumptions": [consumption_dict(c) for c in qs[:200]]})
