import csv
import io
import json
import secrets
import uuid
from datetime import timedelta

import segno
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import OperationalError, connection, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import AccountProfile, Retailer, Vendor
from audit.models import DeviceAuditLog, log_event
from commands.models import DeviceCommand
from commands.services import create_command, expire_stale
from devices.auth import DeviceTokenAuthentication, IsDevice
from devices.crypto import hash_identifier
from devices.models import Customer, Device, DeviceOwnershipTransfer, EnrollmentSession
from devices.ownership import (
    can_access_customer,
    can_access_device,
    can_access_enrollment,
    get_account_type,
    get_ownership_context_for_creator,
    is_superuser_account,
    scope_audit_logs_queryset,
    scope_commands_queryset,
    scope_customers_queryset,
    scope_devices_queryset,
    scope_enrollments_queryset,
)
from entitlements.models import EntitlementAllocation
from entitlements.services import consume_entitlement_for_device, get_account_balance, has_available_entitlement
from notifications.services import notify_commands_available
from roles.permissions import HasPermissionCode, user_has_perm

TESTDPC_COMPONENT = "com.afwsamples.testdpc/com.afwsamples.testdpc.DeviceAdminReceiver"
TESTDPC_URL = "https://dpc.apinfotechandcybersolution.com/download/testdpc.apk"
TESTDPC_CHECKSUM = "gJD2YwtOiWJHkSMkkIfLRlj-quNqG1fb6v100QmzM9w"
ADMIN_COMPONENT = "com.akdevicelock.dpc/com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver"


def luhn_valid(digits: str) -> bool:
    if not digits.isdigit() or not (14 <= len(digits) <= 17):
        return False
    if len(digits) != 15:
        return True
    total = 0
    for i, ch in enumerate(digits):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


class DeviceInfoSerializer(serializers.Serializer):
    device_identifier = serializers.RegexField(r"^[A-Za-z0-9\-]{8,64}$")
    imei = serializers.RegexField(r"^[0-9]{14,17}$", required=False, allow_blank=True)
    manufacturer = serializers.CharField(max_length=64, allow_blank=True, required=False)
    model = serializers.CharField(max_length=64, allow_blank=True, required=False)
    android_version = serializers.CharField(max_length=16, allow_blank=True, required=False)
    sdk_version = serializers.IntegerField(min_value=0, max_value=100, required=False)
    app_version = serializers.CharField(max_length=32, allow_blank=True, required=False)
    fcm_token = serializers.CharField(max_length=512, allow_blank=True, required=False)


class SyncSerializer(DeviceInfoSerializer):
    device_identifier = serializers.CharField(required=False)
    restriction_status = serializers.ChoiceField(choices=Device.Restriction.choices, required=False)


INFO_FIELDS = ["manufacturer", "model", "android_version", "sdk_version", "app_version", "fcm_token"]
LOCK_SCREEN_FIELDS = (
    "emi_amount",
    "emi_due_date",
    "pending_emi_count",
    "dealer_name",
    "dealer_mobile",
    "dealer_company",
)


class DeviceLockScreenUpdateSerializer(serializers.Serializer):
    emi_amount = serializers.CharField(max_length=32, required=False, allow_blank=True, allow_null=True)
    emi_due_date = serializers.CharField(max_length=32, required=False, allow_blank=True, allow_null=True)
    pending_emi_count = serializers.CharField(max_length=16, required=False, allow_blank=True, allow_null=True)
    dealer_name = serializers.CharField(max_length=128, required=False, allow_blank=True, allow_null=True)
    dealer_mobile = serializers.CharField(max_length=32, required=False, allow_blank=True, allow_null=True)
    dealer_company = serializers.CharField(max_length=160, required=False, allow_blank=True, allow_null=True)


def device_dict(d: Device) -> dict:
    return {
        "id": str(d.id),
        "device_identifier": d.device_identifier,
        "registration_reference": d.registration_reference,
        "imei_masked": d.masked_imei(),
        "manufacturer": d.manufacturer,
        "model": d.model,
        "android_version": d.android_version,
        "sdk_version": d.sdk_version,
        "app_version": d.app_version,
        "enrollment_method": d.enrollment_method,
        "enrollment_status": d.enrollment_status,
        "ownership_status": d.ownership_status,
        "connection_status": "ONLINE" if d.is_online else "OFFLINE",
        "restriction_status": d.restriction_status,
        "is_disabled": d.is_disabled,
        "emi_amount": d.emi_amount,
        "emi_due_date": d.emi_due_date,
        "pending_emi_count": d.pending_emi_count,
        "dealer_name": d.dealer_name,
        "dealer_mobile": d.dealer_mobile,
        "dealer_company": d.dealer_company,
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        "registration_date": d.registration_date.isoformat() if d.registration_date else None,
        "released_at": d.released_at.isoformat() if d.released_at else None,
        "customer_id": str(d.customer_id) if d.customer_id else None,
        "customer_name": d.customer.full_name if d.customer_id else None,
        "customer_mobile_masked": d.customer.masked_mobile() if d.customer_id else "",
        "retailer_id": d.retailer_id,
        "retailer_username": d.retailer.username if d.retailer_id else None,
        "vendor_id": d.vendor_id,
        "vendor_username": d.vendor.username if d.vendor_id else None,
        "original_retailer_id": d.original_retailer_id,
        "original_vendor_id": d.original_vendor_id,
        "registered_by_account_id": d.registered_by_account_id,
    }


def customer_dict(c: Customer | None) -> dict | None:
    if c is None:
        return None
    return {
        "id": str(c.id),
        "full_name": c.full_name,
        "mobile_masked": c.masked_mobile(),
        "email_masked": c.masked_email(),
        "retailer_id": c.retailer_id,
        "vendor_id": c.vendor_id,
        "registered_by_account_id": c.registered_by_account_id,
        "device_count": c.devices.count() if hasattr(c, "devices") else 0,
        "created_at": c.created_at.isoformat(),
    }


def enrollment_dict(s: EnrollmentSession) -> dict:
    return {
        "id": str(s.id),
        "status": s.status,
        "enrollment_method": s.enrollment_method,
        "registration_reference": s.registration_reference,
        "superuser_id": s.superuser_id,
        "retailer_id": s.retailer_id,
        "vendor_id": s.vendor_id,
        "created_by_id": s.created_by_id,
        "customer_id": str(s.customer_id) if s.customer_id else None,
        "intended_device_identifier": s.intended_device_identifier,
        "pending_device_id": str(s.pending_device_id) if s.pending_device_id else None,
        "registered_device_id": str(s.registered_device_id) if s.registered_device_id else None,
        "test_dpc_step_completed": s.test_dpc_step_completed,
        "ak_qr_generated": s.ak_qr_generated,
        "bat_downloaded": s.bat_downloaded,
        "failure_reason": s.failure_reason,
        "entitlement_allocated": s.entitlement_allocated,
        "expires_at": s.expires_at.isoformat(),
        "used_at": s.used_at.isoformat() if s.used_at else None,
        "created_at": s.created_at.isoformat(),
    }


class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        s = DeviceInfoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        imei = data.pop("imei", "")

        enroll_token = (
            request.META.get("HTTP_X_ENROLLMENT_TOKEN", "").strip()
            or (request.data.get("enrollment_token") or "").strip()
        )
        legacy_key = request.META.get("HTTP_X_ENROLLMENT_KEY", "").strip()

        for attempt in range(4):
            try:
                return self._register_atomic(request, data, imei, enroll_token, legacy_key)
            except OperationalError:
                if connection.vendor != "sqlite" or attempt == 3:
                    raise
                import time
                time.sleep(0.05 * (attempt + 1))

    def _register_atomic(self, request, data, imei, enroll_token, legacy_key):
        with transaction.atomic():
            if Device.objects.filter(device_identifier=data["device_identifier"]).exists():
                return Response({"error": "already_registered"}, status=status.HTTP_409_CONFLICT)

            session = None
            if enroll_token:
                session = (
                    EnrollmentSession.objects.select_for_update()
                    .filter(token_hash=EnrollmentSession.hash_token(enroll_token))
                    .first()
                )
            elif legacy_key:
                session = (
                    EnrollmentSession.objects.select_for_update()
                    .filter(token_hash=EnrollmentSession.hash_token(legacy_key))
                    .first()
                )

            if session is not None:
                if (
                    not session.is_usable
                    or session.registered_device_id is not None
                    or session.used_at is not None
                    or (session.pending_device_id and session.pending_device.enrollment_status == Device.Enrollment.RELEASED)
                ):
                    if session.status == EnrollmentSession.Status.PENDING and session.expires_at <= timezone.now():
                        session.status = EnrollmentSession.Status.EXPIRED
                        session.token_encrypted = ""
                        session.save(update_fields=["status", "token_encrypted"])
                        if session.pending_device_id and session.pending_device.enrollment_status == Device.Enrollment.PENDING:
                            session.pending_device.enrollment_status = Device.Enrollment.FAILED
                            session.pending_device.save(update_fields=["enrollment_status", "updated_at"])
                    return Response({"error": "invalid_or_expired_enrollment_token"}, status=status.HTTP_403_FORBIDDEN)
                if session.created_by_id and not session.created_by.is_active:
                    session.status = EnrollmentSession.Status.REVOKED
                    session.token_encrypted = ""
                    session.save(update_fields=["status", "token_encrypted"])
                    return Response({"error": "invalid_or_expired_enrollment_token"}, status=status.HTTP_403_FORBIDDEN)
                if session.intended_device_identifier and session.intended_device_identifier != data["device_identifier"]:
                    return Response({"error": "device_identifier_mismatch"}, status=status.HTTP_403_FORBIDDEN)

                quota_owner = session.vendor or session.retailer or session.created_by
                if not has_available_entitlement(quota_owner):
                    return Response({"error": "entitlement_quota_exceeded"}, status=status.HTTP_403_FORBIDDEN)

                now = timezone.now()
                if session.pending_device_id:
                    device = session.pending_device
                    device.device_identifier = data["device_identifier"]
                    for f in INFO_FIELDS:
                        if data.get(f):
                            setattr(device, f, data[f])
                    device.enrollment_status = Device.Enrollment.ENROLLED
                    device.ownership_status = Device.OwnershipStatus.ACTIVE
                    device.registration_date = now
                else:
                    device = Device(
                        **data,
                        registration_reference=session.registration_reference or f"REG-{uuid.uuid4().hex[:8].upper()}",
                        enrollment_method=session.enrollment_method,
                        customer=session.customer,
                        superuser=session.superuser,
                        retailer=session.retailer,
                        vendor=session.vendor,
                        original_retailer=session.retailer,
                        original_vendor=session.vendor,
                        registered_by_account=session.created_by,
                        ownership_status=Device.OwnershipStatus.ACTIVE,
                        registration_date=now,
                    )
                if imei:
                    device.set_imei(imei)
                token = device.issue_token()
                device.touch()
                device.save()

                if not consume_entitlement_for_device(
                    quota_owner, device, registration_reference=device.registration_reference, request=request
                ):
                    transaction.set_rollback(True)
                    return Response({"error": "entitlement_quota_exceeded"}, status=status.HTTP_403_FORBIDDEN)

                session.status = EnrollmentSession.Status.USED
                session.used_at = now
                session.token_encrypted = ""
                session.registered_device = device
                session.save(update_fields=["status", "used_at", "token_encrypted", "registered_device"])
                log_event(
                    device,
                    "DEVICE_REGISTERED",
                    f"{device.manufacturer} {device.model} session={session.id}",
                    actor=session.created_by,
                    request=request,
                )
                return Response({"device_id": str(device.id), "device_token": token}, status=status.HTTP_201_CREATED)

            # Fallback to static deployment enrollment key (Superuser/platform scope)
            if not settings.ENROLLMENT_KEY or not secrets.compare_digest(legacy_key, settings.ENROLLMENT_KEY):
                return Response({"error": "invalid_enrollment_key"}, status=status.HTTP_403_FORBIDDEN)

            platform_su = get_user_model().objects.filter(is_superuser=True, is_active=True).order_by("id").first()
            device = Device(
                **data,
                registration_reference=f"REG-{uuid.uuid4().hex[:8].upper()}",
                superuser=platform_su,
                registered_by_account=platform_su,
                ownership_status=Device.OwnershipStatus.ACTIVE,
                registration_date=timezone.now(),
            )
            if imei:
                device.set_imei(imei)
            token = device.issue_token()
            device.touch()
            device.save()
            log_event(device, "DEVICE_REGISTERED", f"{device.manufacturer} {device.model}", request=request)
            return Response({"device_id": str(device.id), "device_token": token}, status=status.HTTP_201_CREATED)


class DeviceBase(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]


class SyncView(DeviceBase):
    def post(self, request):
        device = request.user.device
        s = SyncSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        for f in INFO_FIELDS:
            if f in data:
                setattr(device, f, data[f])
        if "restriction_status" in data and device.restriction_status not in (
            Device.Restriction.LOCK_PENDING,
            Device.Restriction.UNLOCK_PENDING,
            Device.Restriction.RELEASE_PENDING,
        ):
            device.restriction_status = data["restriction_status"]
        device.touch()
        device.save()
        expire_stale(device)
        pending = device.commands.filter(
            command_status__in=[DeviceCommand.Status.PENDING, DeviceCommand.Status.DELIVERED]
        ).count()
        log_event(device, "DEVICE_SYNC", f"pending={pending}")
        return Response({
            "server_time": int(timezone.now().timestamp()),
            "pending_commands": pending,
            "lock_screen": device.lock_screen_info(),
        })


class StatusView(DeviceBase):
    def get(self, request):
        device = request.user.device
        data = device_dict(device)
        data["lock_screen"] = device.lock_screen_info()
        return Response(data)


class RenewTokenView(DeviceBase):
    def post(self, request):
        device = request.user.device
        token = device.issue_token()
        device.save(update_fields=["auth_token_hash", "updated_at"])
        log_event(device, "CREDENTIAL_RENEWED")
        return Response({"device_token": token})


class OperatorBase(APIView):
    """RBAC-protected and tenant-ownership-enforced operator base view."""
    permission_classes = [HasPermissionCode]
    required_permission = "devices.view"

    def get_device(self, request, device_id) -> Device:
        device = get_object_or_404(Device.objects.select_related("customer", "retailer", "vendor"), pk=device_id)
        if not can_access_device(request.user, device):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"device={device_id}", request=request,
                      target_type="device", target_id=str(device_id))
            raise PermissionDenied("Device is outside your ownership boundary.")
        return device


def _apply_device_filters(qs, params, user):
    if is_superuser_account(user):
        if params.get("retailer_id"):
            qs = qs.filter(retailer_id=params["retailer_id"])
        if params.get("vendor_id"):
            qs = qs.filter(vendor_id=params["vendor_id"])
        acct_type = params.get("account_type")
        if acct_type == AccountProfile.AccountType.VENDOR:
            qs = qs.filter(vendor__isnull=False)
        elif acct_type == AccountProfile.AccountType.RETAILER:
            qs = qs.filter(retailer__isnull=False, vendor__isnull=True)
    if params.get("enrollment_status"):
        qs = qs.filter(enrollment_status=params["enrollment_status"])
    if params.get("restriction_status"):
        qs = qs.filter(restriction_status=params["restriction_status"])
    if params.get("ownership_status"):
        qs = qs.filter(ownership_status=params["ownership_status"])
    if params.get("android_version"):
        qs = qs.filter(android_version__iexact=params["android_version"])
    if params.get("brand"):
        qs = qs.filter(manufacturer__icontains=params["brand"])
    if params.get("model"):
        qs = qs.filter(model__icontains=params["model"])
    if params.get("is_disabled") in ("true", "false", "1", "0"):
        qs = qs.filter(is_disabled=params["is_disabled"] in ("true", "1"))
    if params.get("registered_from"):
        qs = qs.filter(registration_date__date__gte=params["registered_from"])
    if params.get("registered_to"):
        qs = qs.filter(registration_date__date__lte=params["registered_to"])
    if params.get("last_seen_from"):
        qs = qs.filter(last_seen__date__gte=params["last_seen_from"])
    if params.get("last_seen_to"):
        qs = qs.filter(last_seen__date__lte=params["last_seen_to"])
    q = (params.get("q") or "").strip()
    if q:
        h = hash_identifier(q)
        qs = qs.filter(
            Q(device_identifier__icontains=q)
            | Q(registration_reference__icontains=q)
            | Q(model__icontains=q)
            | Q(manufacturer__icontains=q)
            | Q(customer__full_name__icontains=q)
            | Q(imei_hash=h)
            | Q(customer__mobile_hash=h)
        )
    conn = params.get("connection_status")
    if conn in ("ONLINE", "OFFLINE"):
        cutoff = timezone.now() - timedelta(seconds=settings.ONLINE_WINDOW_SECONDS)
        qs = qs.filter(last_seen__gte=cutoff) if conn == "ONLINE" else qs.filter(Q(last_seen__lt=cutoff) | Q(last_seen__isnull=True))
    return qs


class DeviceListView(OperatorBase):
    required_permission = "devices.view"

    def get(self, request):
        qs = scope_devices_queryset(request.user).select_related("customer", "retailer", "vendor").order_by("-created_at")
        qs = _apply_device_filters(qs, request.GET, request.user)
        try:
            page = max(1, int(request.GET.get("page", 1)))
            page_size = min(200, max(1, int(request.GET.get("page_size", 25))))
        except ValueError:
            page, page_size = 1, 25
        total = qs.count()
        items = qs[(page - 1) * page_size : page * page_size]
        return Response({
            "count": total,
            "page": page,
            "page_size": page_size,
            "devices": [device_dict(d) for d in items],
        })


class DeviceExportView(OperatorBase):
    required_permission = "devices.view"

    def get(self, request):
        qs = scope_devices_queryset(request.user).select_related("customer", "retailer", "vendor").order_by("-created_at")
        qs = _apply_device_filters(qs, request.GET, request.user)
        if request.GET.get("format") == "json":
            return Response({"devices": [device_dict(d) for d in qs]})
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "id", "registration_reference", "device_identifier", "imei_masked", "model",
            "enrollment_status", "ownership_status", "restriction_status", "customer_name", "retailer_id", "vendor_id",
        ])
        for d in qs:
            writer.writerow([
                str(d.id), d.registration_reference, d.device_identifier, d.masked_imei(), d.model,
                d.enrollment_status, d.ownership_status, d.restriction_status,
                d.customer.full_name if d.customer_id else "", d.retailer_id or "", d.vendor_id or "",
            ])
        resp = HttpResponse(buf.getvalue(), content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="devices_export.csv"'
        return resp


class DeviceInfoView(OperatorBase):
    required_permission = "devices.view"

    def get(self, request, device_id):
        device = self.get_device(request, device_id)
        data = device_dict(device)
        last = device.commands.first()
        data["last_command"] = None if not last else {
            "id": str(last.id), "type": last.command_type, "status": last.command_status,
            "result": last.execution_result,
        }
        return Response(data)

    def patch(self, request, device_id):
        device = self.get_device(request, device_id)
        s = DeviceLockScreenUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        updated_fields = []
        for f in LOCK_SCREEN_FIELDS:
            if f in s.validated_data:
                setattr(device, f, (s.validated_data[f] or "").strip())
                updated_fields.append(f)
        if updated_fields:
            device.save(update_fields=[*updated_fields, "updated_at"])
            log_event(device, "LOCK_SCREEN_INFO_UPDATED", ",".join(updated_fields), request=request)
        return Response({"device": device_dict(device)})


class DeviceRevealImeiView(OperatorBase):
    required_permission = "devices.view"

    def get(self, request, device_id):
        device = self.get_device(request, device_id)
        log_event(device, "PII_REVEALED", "imei", request=request)
        return Response({"device_id": str(device.id), "imei": device.get_imei()})


class OperatorCommandView(OperatorBase):
    command_type = None
    required_permission = "devices.sync"

    def post(self, request, device_id):
        device = self.get_device(request, device_id)
        if device.enrollment_status == Device.Enrollment.RELEASED:
            return Response({"error": "device_released"}, status=status.HTTP_409_CONFLICT)
        if device.enrollment_status in (Device.Enrollment.PENDING, Device.Enrollment.FAILED):
            return Response({"error": "device_not_enrolled"}, status=status.HTTP_409_CONFLICT)
        expire_stale(device)
        existing = device.commands.filter(
            command_type=self.command_type,
            command_status__in=[DeviceCommand.Status.PENDING, DeviceCommand.Status.DELIVERED],
        ).first()
        if existing:
            return Response({"command_id": str(existing.id), "status": existing.command_status, "duplicate": True})
        cmd = create_command(
            device,
            self.command_type,
            request.data.get("reason", ""),
            request.data.get("ttl_seconds"),
            request=request,
        )
        if self.command_type == DeviceCommand.Type.LOCK and device.restriction_status == Device.Restriction.NONE:
            device.restriction_status = Device.Restriction.LOCK_PENDING
            device.save(update_fields=["restriction_status", "updated_at"])
        elif self.command_type == DeviceCommand.Type.UNLOCK and device.restriction_status == Device.Restriction.LOCKED:
            device.restriction_status = Device.Restriction.UNLOCK_PENDING
            device.save(update_fields=["restriction_status", "updated_at"])
        elif self.command_type == DeviceCommand.Type.RELEASE:
            device.restriction_status = Device.Restriction.RELEASE_PENDING
            device.save(update_fields=["restriction_status", "updated_at"])

        fcm_sent = notify_commands_available(device)
        return Response(
            {
                "command_id": str(cmd.id),
                "status": cmd.command_status,
                "device_restriction_status": device.restriction_status,
                "key_id": cmd.key_id,
                "device_online": device.is_online,
                "fcm_notified": fcm_sent,
            },
            status=status.HTTP_201_CREATED,
        )


class LockView(OperatorCommandView):
    command_type = DeviceCommand.Type.LOCK
    required_permission = "devices.lock"


class UnlockView(OperatorCommandView):
    command_type = DeviceCommand.Type.UNLOCK
    required_permission = "devices.unlock"


class ReleaseView(OperatorCommandView):
    command_type = DeviceCommand.Type.RELEASE
    required_permission = "devices.release"


class SyncCommandView(OperatorCommandView):
    command_type = DeviceCommand.Type.SYNC
    required_permission = "devices.sync"


class StatusCommandView(OperatorCommandView):
    command_type = DeviceCommand.Type.STATUS
    required_permission = "devices.sync"


class TransferSerializer(serializers.Serializer):
    to_retailer_id = serializers.IntegerField(required=True)
    to_vendor_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    reason = serializers.CharField(min_length=3, max_length=300)
    confirm = serializers.BooleanField()


class DeviceTransferView(OperatorBase):
    required_permission = "devices.transfer"

    def post(self, request, device_id):
        if not is_superuser_account(request.user):
            return Response({"error": "superuser_required_for_transfer"}, status=status.HTTP_403_FORBIDDEN)
        device = self.get_device(request, device_id)
        s = TransferSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if not d["confirm"]:
            return Response({"error": "explicit_confirmation_required"}, status=status.HTTP_400_BAD_REQUEST)

        User = get_user_model()
        to_retailer = get_object_or_404(User, pk=d["to_retailer_id"])
        ret_prof = AccountProfile.objects.filter(user=to_retailer).first()
        if not ret_prof or ret_prof.account_type != AccountProfile.AccountType.RETAILER:
            return Response({"error": "invalid_target_retailer"}, status=status.HTTP_400_BAD_REQUEST)

        to_vendor = None
        if d["to_vendor_id"] is not None:
            to_vendor = get_object_or_404(User, pk=d["to_vendor_id"])
            ven_prof = AccountProfile.objects.filter(user=to_vendor).first()
            if (
                not ven_prof
                or ven_prof.account_type != AccountProfile.AccountType.VENDOR
                or ven_prof.retailer_id != to_retailer.id
            ):
                return Response({"error": "invalid_target_vendor"}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            transfer = DeviceOwnershipTransfer.objects.create(
                device=device,
                from_retailer=device.retailer,
                from_vendor=device.vendor,
                to_retailer=to_retailer,
                to_vendor=to_vendor,
                transferred_by=request.user,
                reason=d["reason"],
            )
            if device.original_retailer_id is None:
                device.original_retailer = device.retailer
            if device.original_vendor_id is None:
                device.original_vendor = device.vendor
            device.retailer = to_retailer
            device.vendor = to_vendor
            device._transfer_authorized = True
            if device.enrollment_status != Device.Enrollment.RELEASED:
                device.ownership_status = Device.OwnershipStatus.TRANSFERRED
            device.save(update_fields=[
                "original_retailer", "original_vendor", "retailer", "vendor", "ownership_status", "updated_at"
            ])
            log_event(
                device,
                "DEVICE_OWNERSHIP_TRANSFERRED",
                f"from=({transfer.from_retailer_id},{transfer.from_vendor_id}) "
                f"to=({to_retailer.id},{to_vendor.id if to_vendor else None}) reason={d['reason']}",
                request=request,
            )
        return Response({"transfer_id": str(transfer.id), "device": device_dict(device)})


class CustomerCreateSerializer(serializers.Serializer):
    full_name = serializers.CharField(min_length=1, max_length=128)
    mobile = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")


class CustomerListCreateView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "customers.view"

    def get(self, request):
        qs = scope_customers_queryset(request.user).order_by("-created_at")
        q = (request.GET.get("q") or "").strip()
        if q:
            h = hash_identifier(q)
            qs = qs.filter(Q(full_name__icontains=q) | Q(mobile_hash=h) | Q(email_hash=h.lower()))
        return Response({"customers": [customer_dict(c) for c in qs[:200]]})

    def post(self, request):
        if not user_has_perm(request.user, "customers.manage"):
            return Response({"error": "missing_permission"}, status=status.HTTP_403_FORBIDDEN)
        s = CustomerCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        _, retailer, vendor = get_ownership_context_for_creator(request.user)
        c = Customer(
            full_name=d["full_name"],
            retailer=retailer,
            vendor=vendor,
            registered_by_account=request.user,
        )
        if d["mobile"]:
            c.set_mobile(d["mobile"])
        if d["email"]:
            c.set_email(d["email"])
        c.save()
        log_event(None, "CUSTOMER_CREATED", f"customer_id={c.id}", request=request,
                  target_type="customer", target_id=str(c.id))
        return Response(customer_dict(c), status=status.HTTP_201_CREATED)


class CustomerDetailView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "customers.view"

    def get(self, request, customer_id):
        customer = get_object_or_404(Customer, pk=customer_id)
        if not can_access_customer(request.user, customer):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"customer={customer_id}", request=request,
                      target_type="customer", target_id=str(customer_id))
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return Response(customer_dict(customer))


class CustomerRevealView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "customers.view"

    def get(self, request, customer_id):
        customer = get_object_or_404(Customer, pk=customer_id)
        if not can_access_customer(request.user, customer):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        log_event(None, "PII_REVEALED", f"customer={customer_id}", request=request,
                  target_type="customer", target_id=str(customer_id))
        return Response({
            "id": str(customer.id),
            "full_name": customer.full_name,
            "mobile": customer.get_mobile(),
            "email": customer.get_email(),
        })


class RegistrationCreateSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    customer_mobile = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    customer_email = serializers.EmailField(required=False, allow_blank=True, default="")
    brand = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    model = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    imei = serializers.CharField(max_length=17, required=False, allow_blank=True, default="")
    android_version = serializers.CharField(max_length=16, required=False, allow_blank=True, default="14")
    emi_amount = serializers.CharField(max_length=32, required=False, allow_blank=True, allow_null=True, default="")
    emi_due_date = serializers.CharField(max_length=32, required=False, allow_blank=True, allow_null=True, default="")
    pending_emi_count = serializers.CharField(max_length=16, required=False, allow_blank=True, allow_null=True, default="")
    dealer_name = serializers.CharField(max_length=128, required=False, allow_blank=True, allow_null=True, default="")
    dealer_mobile = serializers.CharField(max_length=32, required=False, allow_blank=True, allow_null=True, default="")
    dealer_company = serializers.CharField(max_length=160, required=False, allow_blank=True, allow_null=True, default="")
    enrollment_method = serializers.ChoiceField(
        choices=Device.EnrollmentMethod.choices,
        required=False,
        default=Device.EnrollmentMethod.QR_9_15,
    )
    ttl_seconds = serializers.IntegerField(min_value=60, max_value=86400, required=False, default=900)

    def validate_imei(self, val):
        cleaned = (val or "").strip()
        if not cleaned:
            return ""
        if not luhn_valid(cleaned):
            raise serializers.ValidationError("Invalid IMEI format or checksum.")
        return cleaned

    def validate_android_version(self, val):
        v = (val or "").strip() or "14"
        try:
            major = int(v.split(".")[0])
        except ValueError:
            raise serializers.ValidationError("Invalid Android version.")
        if major < 9:
            raise serializers.ValidationError("Android 8 and below are not supported (minSdk 28 / Android 9+).")
        return v


class RegistrationCreateView(APIView):
    """Guided registration: validates Customer + Device + Entitlement balance WITHOUT consuming entitlement yet."""
    permission_classes = [HasPermissionCode]
    required_permission = "enrollments.manage"

    def post(self, request):
        s = RegistrationCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        if not has_available_entitlement(request.user):
            return Response({"error": "entitlement_quota_exceeded"}, status=status.HTTP_403_FORBIDDEN)

        su, retailer, vendor = get_ownership_context_for_creator(request.user)
        reg_ref = f"REG-{uuid.uuid4().hex[:8].upper()}"

        with transaction.atomic():
            customer = None
            if d["customer_name"] or d["customer_mobile"] or d["customer_email"]:
                customer = Customer(
                    full_name=d["customer_name"] or d["customer_mobile"] or d["customer_email"],
                    retailer=retailer,
                    vendor=vendor,
                    registered_by_account=request.user,
                )
                if d["customer_mobile"]:
                    customer.set_mobile(d["customer_mobile"])
                if d["customer_email"]:
                    customer.set_email(d["customer_email"])
                customer.save()

            pending_dev = Device(
                device_identifier=f"pending-{uuid.uuid4().hex[:16]}",
                registration_reference=reg_ref,
                manufacturer=d["brand"],
                model=d["model"],
                android_version=d["android_version"],
                emi_amount=(d.get("emi_amount") or "").strip(),
                emi_due_date=(d.get("emi_due_date") or "").strip(),
                pending_emi_count=(d.get("pending_emi_count") or "").strip(),
                dealer_name=(d.get("dealer_name") or "").strip(),
                dealer_mobile=(d.get("dealer_mobile") or "").strip(),
                dealer_company=(d.get("dealer_company") or "").strip(),
                enrollment_method=d["enrollment_method"],
                enrollment_status=Device.Enrollment.PENDING,
                ownership_status=Device.OwnershipStatus.ACTIVE,
                customer=customer,
                superuser=su,
                retailer=retailer,
                vendor=vendor,
                original_retailer=retailer,
                original_vendor=vendor,
                registered_by_account=request.user,
            )
            if d["imei"]:
                pending_dev.set_imei(d["imei"])
            pending_dev.auth_token_hash = Device.hash_token(secrets.token_urlsafe(32))
            pending_dev.save()

            session, raw_token = EnrollmentSession.create_session(
                created_by=request.user,
                superuser=su,
                retailer=retailer,
                vendor=vendor,
                customer=customer,
                enrollment_method=d["enrollment_method"],
                registration_reference=reg_ref,
                pending_device=pending_dev,
                ttl_seconds=d["ttl_seconds"],
            )
            log_event(
                pending_dev,
                "PENDING_REGISTRATION_CREATED",
                f"ref={reg_ref} method={d['enrollment_method']}",
                request=request,
            )

        return Response(
            {
                "registration_reference": reg_ref,
                "customer": customer_dict(customer),
                "device": device_dict(pending_dev),
                "enrollment_session": enrollment_dict(session),
                "enrollment_token": raw_token,
            },
            status=status.HTTP_201_CREATED,
        )


class EnrollmentCreateSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    customer_name = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    customer_mobile = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    customer_email = serializers.EmailField(required=False, allow_blank=True, default="")
    intended_device_identifier = serializers.RegexField(
        r"^[A-Za-z0-9\-]{8,64}$", required=False, allow_blank=True, default=""
    )
    enrollment_method = serializers.ChoiceField(
        choices=Device.EnrollmentMethod.choices,
        required=False,
        default=Device.EnrollmentMethod.QR_9_15,
    )
    ttl_seconds = serializers.IntegerField(min_value=60, max_value=86400, required=False, default=900)


class EnrollmentListCreateView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "enrollments.manage"

    def get(self, request):
        qs = scope_enrollments_queryset(request.user).order_by("-created_at")
        return Response({"enrollments": [enrollment_dict(e) for e in qs[:100]]})

    def post(self, request):
        s = EnrollmentCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if not has_available_entitlement(request.user):
            return Response({"error": "entitlement_quota_exceeded"}, status=status.HTTP_403_FORBIDDEN)
        su, retailer, vendor = get_ownership_context_for_creator(request.user)

        customer = None
        if d["customer_id"]:
            customer = get_object_or_404(Customer, pk=d["customer_id"])
            if not can_access_customer(request.user, customer):
                return Response({"error": "forbidden_customer"}, status=status.HTTP_403_FORBIDDEN)
        elif d["customer_name"]:
            customer = Customer(
                full_name=d["customer_name"],
                retailer=retailer,
                vendor=vendor,
                registered_by_account=request.user,
            )
            if d["customer_mobile"]:
                customer.set_mobile(d["customer_mobile"])
            if d["customer_email"]:
                customer.set_email(d["customer_email"])
            customer.save()

        session, raw_token = EnrollmentSession.create_session(
            created_by=request.user,
            superuser=su,
            retailer=retailer,
            vendor=vendor,
            customer=customer,
            intended_device_identifier=d["intended_device_identifier"],
            enrollment_method=d["enrollment_method"],
            registration_reference=f"REG-{uuid.uuid4().hex[:8].upper()}",
            ttl_seconds=d["ttl_seconds"],
        )
        log_event(None, "ENROLLMENT_SESSION_CREATED", f"session={session.id}", request=request,
                  target_type="enrollment", target_id=str(session.id))
        resp = enrollment_dict(session)
        resp["enrollment_token"] = raw_token
        return Response(resp, status=status.HTTP_201_CREATED)


class EnrollmentDetailView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "enrollments.manage"

    def get(self, request, session_id):
        session = get_object_or_404(EnrollmentSession, pk=session_id)
        if not can_access_enrollment(request.user, session):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"enrollment={session_id}", request=request)
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return Response(enrollment_dict(session))


class EnrollmentStatusView(EnrollmentDetailView):
    def get(self, request, session_id):
        session = get_object_or_404(EnrollmentSession, pk=session_id)
        if not can_access_enrollment(request.user, session):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        if session.status == EnrollmentSession.Status.PENDING and session.expires_at <= timezone.now():
            session.status = EnrollmentSession.Status.EXPIRED
            session.token_encrypted = ""
            session.save(update_fields=["status", "token_encrypted"])
            if session.pending_device_id and session.pending_device.enrollment_status == Device.Enrollment.PENDING:
                session.pending_device.enrollment_status = Device.Enrollment.FAILED
                session.pending_device.save(update_fields=["enrollment_status", "updated_at"])
        data = enrollment_dict(session)
        data["entitlement_consumed"] = bool(session.registered_device_id)
        return Response(data)


class EnrollmentCompleteStepView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "enrollments.manage"

    def post(self, request, session_id):
        session = get_object_or_404(EnrollmentSession, pk=session_id)
        if not can_access_enrollment(request.user, session):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        step = request.data.get("step", "test_dpc")
        if step == "test_dpc":
            session.test_dpc_step_completed = True
            session.save(update_fields=["test_dpc_step_completed"])
        return Response(enrollment_dict(session))


class EnrollmentCancelView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "enrollments.manage"

    def post(self, request, session_id):
        session = get_object_or_404(EnrollmentSession, pk=session_id)
        if not can_access_enrollment(request.user, session):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        if session.status == EnrollmentSession.Status.USED:
            return Response({"error": "already_completed"}, status=status.HTTP_409_CONFLICT)
        session.status = EnrollmentSession.Status.REVOKED
        session.token_encrypted = ""
        session.failure_reason = str(request.data.get("reason", "cancelled_by_operator"))[:255]
        session.save(update_fields=["status", "token_encrypted", "failure_reason"])
        if session.pending_device_id and session.pending_device.enrollment_status == Device.Enrollment.PENDING:
            session.pending_device.enrollment_status = Device.Enrollment.FAILED
            session.pending_device.save(update_fields=["enrollment_status", "updated_at"])
        log_event(None, "ENROLLMENT_CANCELLED", f"session={session.id}", request=request,
                  target_type="enrollment", target_id=str(session.id))
        return Response(enrollment_dict(session))


class EnrollmentQRView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "enrollments.manage"

    def get(self, request, session_id):
        session = get_object_or_404(EnrollmentSession, pk=session_id)
        if not can_access_enrollment(request.user, session):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"enrollment_qr={session_id}", request=request)
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        if not session.is_usable:
            if session.status == EnrollmentSession.Status.PENDING and session.expires_at <= timezone.now():
                session.status = EnrollmentSession.Status.EXPIRED
                session.token_encrypted = ""
                session.save(update_fields=["status", "token_encrypted"])
            return Response({"error": "enrollment_session_not_usable"}, status=status.HTTP_409_CONFLICT)
        raw_token = session.get_raw_token()
        if not raw_token:
            return Response({"error": "enrollment_session_not_usable"}, status=status.HTTP_409_CONFLICT)

        step = request.GET.get("step", "akdl")
        base = f"{request.scheme}://{request.get_host()}" if settings.PUBLIC_BASE_URL == "auto" else settings.PUBLIC_BASE_URL
        if step == "testdpc":
            payload = {
                "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME": TESTDPC_COMPONENT,
                "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION": TESTDPC_URL,
                "android.app.extra.PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM": TESTDPC_CHECKSUM,
                "android.app.extra.PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED": True,
                "android.app.extra.PROVISIONING_SKIP_ENCRYPTION": True,
            }
        else:
            payload = {
                "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME": ADMIN_COMPONENT,
                "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION": f"{base.rstrip('/')}/download/akdevicelock.apk",
                "android.app.extra.PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM": settings.APK_CERT_SHA256,
                "android.app.extra.PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED": True,
                "android.app.extra.PROVISIONING_SKIP_ENCRYPTION": True,
                "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE": {
                    "server_url": base.rstrip("/"),
                    "enrollment_key": raw_token,
                    "enrollment_session_id": str(session.id),
                },
            }
            if not session.ak_qr_generated:
                session.ak_qr_generated = True
                session.save(update_fields=["ak_qr_generated"])

        log_event(None, "QR_GENERATED", f"session={session.id} step={step}", request=request,
                  target_type="enrollment", target_id=str(session.id))
        svg = segno.make(json.dumps(payload, separators=(",", ":")), error="m").svg_inline(scale=4, border=3)
        if request.GET.get("format") == "json" or "application/json" in request.META.get("HTTP_ACCEPT", ""):
            return Response({"step": step, "session_id": str(session.id), "svg": svg, "expires_at": session.expires_at.isoformat()})
        return HttpResponse(svg, content_type="image/svg+xml")


class EnrollmentBatView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "enrollments.manage"

    def get(self, request, session_id):
        session = get_object_or_404(EnrollmentSession, pk=session_id)
        if not can_access_enrollment(request.user, session):
            log_event(None, "UNAUTHORIZED_ACCESS_ATTEMPT", f"enrollment_bat={session_id}", request=request)
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        if not session.is_usable:
            if session.status == EnrollmentSession.Status.PENDING and session.expires_at <= timezone.now():
                session.status = EnrollmentSession.Status.EXPIRED
                session.token_encrypted = ""
                session.save(update_fields=["status", "token_encrypted"])
            return Response({"error": "enrollment_session_not_usable"}, status=status.HTTP_409_CONFLICT)
        raw_token = session.get_raw_token()
        if not raw_token:
            return Response({"error": "enrollment_session_not_usable"}, status=status.HTTP_409_CONFLICT)

        base = (
            f"{request.scheme}://{request.get_host()}"
            if settings.PUBLIC_BASE_URL == "auto"
            else settings.PUBLIC_BASE_URL
        ).rstrip("/")
        apk_url = f"{base}/download/akdevicelock.apk"
        bat = "\r\n".join([
            "@echo off",
            "setlocal EnableDelayedExpansion",
            "echo ============================================================",
            f"echo AK DeviceLock Android 16 Provisioning (Session {session.id})",
            "echo Prerequisites: Factory-fresh device, 0 Google/Samsung accounts,",
            "echo Samsung Auto Blocker OFF, USB Debugging ON and authorized.",
            "echo ============================================================",
            "",
            "where adb >nul 2>nul",
            "if errorlevel 1 (",
            "  if exist \"%LOCALAPPDATA%\\Android\\Sdk\\platform-tools\\adb.exe\" (",
            "    set \"PATH=%LOCALAPPDATA%\\Android\\Sdk\\platform-tools;%PATH%\"",
            "  ) else (",
            "    echo [ERROR] ADB not found in PATH. Install Android Platform Tools.",
            "    goto :fail",
            "  )",
            ")",
            "",
            "for /f \"delims=\" %%S in ('adb get-state 2^>^&1') do set ADB_STATE=%%S",
            "if /i not \"!ADB_STATE!\"==\"device\" (",
            "  echo [ERROR] Device not ready. Current state: !ADB_STATE!",
            "  echo Ensure USB cable is connected, USB Debugging is ON, and RSA prompt is accepted.",
            "  goto :fail",
            ")",
            "",
            "for /f \"delims=\" %%V in ('adb shell getprop ro.build.version.sdk 2^>nul') do set SDK_VER=%%V",
            "echo Detected Android SDK: !SDK_VER!",
            "",
            "adb shell dumpsys account | findstr /i /c:\"Account {\" >nul 2>nul",
            "if not errorlevel 1 (",
            "  echo [ERROR] Existing user accounts detected on device.",
            "  echo Remove all Google/Samsung accounts or factory reset before Device Owner setup.",
            "  goto :fail",
            ")",
            "",
            "adb shell pm path com.akdevicelock.dpc >nul 2>nul",
            "if errorlevel 1 (",
            f"  echo [INFO] Installing AK DeviceLock APK from {apk_url} ...",
            f"  curl -fsSL -o \"%TEMP%\\akdevicelock_{session.id}.apk\" \"{apk_url}\"",
            f"  if errorlevel 1 ( echo [ERROR] Failed to download APK. & goto :fail )",
            f"  adb install -r \"%TEMP%\\akdevicelock_{session.id}.apk\" || adb install --no-streaming -r \"%TEMP%\\akdevicelock_{session.id}.apk\"",
            "  if errorlevel 1 ( echo [ERROR] APK install failed. Disable Auto Blocker and retry. & goto :fail )",
            ")",
            "",
            "adb shell dpm set-device-owner com.akdevicelock.dpc/.deviceadmin.AkDeviceAdminReceiver",
            "if errorlevel 1 (",
            "  echo [ERROR] dpm set-device-owner failed. Device Owner was NOT granted.",
            "  goto :fail",
            ")",
            "",
            "adb shell dpm list-owners | findstr /i \"com.akdevicelock.dpc\" >nul 2>nul",
            "if errorlevel 1 (",
            "  echo [ERROR] Verification failed: com.akdevicelock.dpc is not listed as Device Owner.",
            "  goto :fail",
            ")",
            "",
            f"adb shell am start -n com.akdevicelock.dpc/.status.MainActivity --es server_url \"{base}\" --es enrollment_key \"{raw_token}\"",
            "if errorlevel 1 (",
            "  echo [ERROR] Failed to launch AK DeviceLock with session credentials.",
            "  goto :fail",
            ")",
            "",
            "echo [SUCCESS] Device Owner verified and AK DeviceLock launched for registration.",
            "echo.",
            "pause",
            "exit /b 0",
            "",
            ":fail",
            "echo.",
            "pause",
            "exit /b 1",
            "",
        ])
        if not session.bat_downloaded:
            session.bat_downloaded = True
            session.save(update_fields=["bat_downloaded"])
        log_event(None, "BAT_DOWNLOADED", f"session={session.id}", request=request,
                  target_type="enrollment", target_id=str(session.id))
        resp = HttpResponse(bat, content_type="text/plain")
        resp["Content-Disposition"] = f'attachment; filename="provision_{session.id}.bat"'
        return resp


class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        acct_type = get_account_type(request.user)
        devs = scope_devices_queryset(request.user)
        cutoff = timezone.now() - timedelta(seconds=settings.ONLINE_WINDOW_SECONDS)
        total_devices = devs.count()
        online = devs.filter(last_seen__gte=cutoff, enrollment_status=Device.Enrollment.ENROLLED).count()
        locked = devs.filter(restriction_status=Device.Restriction.LOCKED).count()
        released = devs.filter(enrollment_status=Device.Enrollment.RELEASED).count()
        pending_enroll = devs.filter(enrollment_status=Device.Enrollment.PENDING).count()
        active_devices = devs.filter(enrollment_status=Device.Enrollment.ENROLLED, is_disabled=False).count()
        inactive_devices = total_devices - active_devices - released

        bal = get_account_balance(request.user)
        data = {
            "account_type": acct_type,
            "devices": {
                "total": total_devices,
                "active": active_devices,
                "inactive": max(0, inactive_devices),
                "online": online,
                "locked": locked,
                "released": released,
                "pending_enrollment": pending_enroll,
            },
            "entitlements": bal,
        }
        if acct_type == AccountProfile.AccountType.SUPERUSER:
            data["retailers_count"] = Retailer.objects.count()
            data["vendors_count"] = Vendor.objects.count()
            data["expiring_allocations"] = EntitlementAllocation.objects.filter(
                status=EntitlementAllocation.Status.ACTIVE,
                expires_at__lte=timezone.now() + timedelta(days=30),
            ).count()
        elif acct_type == AccountProfile.AccountType.RETAILER:
            data["vendors_count"] = Vendor.objects.filter(retailer__account=request.user).count()
            data["expiring_allocations"] = EntitlementAllocation.objects.filter(
                allocated_to=request.user,
                status=EntitlementAllocation.Status.ACTIVE,
                expires_at__lte=timezone.now() + timedelta(days=30),
            ).count()
        else:
            data["expiring_allocations"] = EntitlementAllocation.objects.filter(
                allocated_to=request.user,
                status=EntitlementAllocation.Status.ACTIVE,
                expires_at__lte=timezone.now() + timedelta(days=30),
            ).count()
        return Response(data)


class CommandHistoryView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "commands.view"

    def get(self, request):
        qs = scope_commands_queryset(request.user).select_related("device", "issued_by")[:100]
        return Response({
            "commands": [
                {
                    "id": str(c.id),
                    "device_id": str(c.device_id),
                    "device_identifier": c.device.device_identifier,
                    "device_model": f"{c.device.manufacturer} {c.device.model}".strip(),
                    "command_type": c.command_type,
                    "command_status": c.command_status,
                    "created_by": c.issued_by.username if c.issued_by_id else None,
                    "issued_at": c.issued_at.isoformat(),
                    "expires_at": c.expires_at.isoformat(),
                    "executed_at": c.executed_at.isoformat() if c.executed_at else None,
                    "execution_result": c.execution_result,
                }
                for c in qs
            ]
        })


class AuditHistoryView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "audit.view"

    def get(self, request):
        qs = scope_audit_logs_queryset(request.user).select_related("actor", "device")
        if request.GET.get("event"):
            qs = qs.filter(event=request.GET["event"])
        if request.GET.get("actor"):
            qs = qs.filter(actor__username__icontains=request.GET["actor"])
        return Response({
            "audit_logs": [
                {
                    "id": a.id,
                    "event": a.event,
                    "result": a.result,
                    "actor": a.actor.username if a.actor_id else None,
                    "device_id": str(a.device_id) if a.device_id else None,
                    "target_type": a.target_type,
                    "target_id": a.target_id,
                    "retailer_id": a.retailer_id,
                    "vendor_id": a.vendor_id,
                    "source_ip": a.source_ip,
                    "client_device": a.client_device,
                    "user_agent": a.user_agent,
                    "timestamp": a.timestamp.isoformat(),
                }
                for a in qs[:200]
            ]
        })
