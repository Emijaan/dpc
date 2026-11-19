import secrets

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import log_event
from commands.models import DeviceCommand
from commands.services import create_command, expire_stale
from devices.auth import DeviceTokenAuthentication, IsDevice
from devices.models import Device


class DeviceInfoSerializer(serializers.Serializer):
    device_identifier = serializers.RegexField(r"^[A-Za-z0-9\-]{8,64}$")
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


def device_dict(d: Device) -> dict:
    return {
        "id": str(d.id), "device_identifier": d.device_identifier, "manufacturer": d.manufacturer,
        "model": d.model, "android_version": d.android_version, "sdk_version": d.sdk_version,
        "app_version": d.app_version, "enrollment_status": d.enrollment_status,
        "connection_status": "ONLINE" if d.is_online else "OFFLINE",
        "restriction_status": d.restriction_status,
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
    }


class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        key = request.META.get("HTTP_X_ENROLLMENT_KEY", "")
        if not settings.ENROLLMENT_KEY or not secrets.compare_digest(key, settings.ENROLLMENT_KEY):
            return Response({"error": "invalid_enrollment_key"}, status=status.HTTP_403_FORBIDDEN)
        s = DeviceInfoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        if Device.objects.filter(device_identifier=data["device_identifier"]).exists():
            return Response({"error": "already_registered"}, status=status.HTTP_409_CONFLICT)
        device = Device(**data)
        token = device.issue_token()
        device.touch()
        device.save()
        log_event(device, "DEVICE_REGISTERED", f"{device.manufacturer} {device.model}")
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
        if "restriction_status" in data:
            device.restriction_status = data["restriction_status"]
        device.touch()
        device.save()
        expire_stale(device)
        pending = device.commands.filter(
            command_status__in=[DeviceCommand.Status.PENDING, DeviceCommand.Status.DELIVERED]).count()
        log_event(device, "DEVICE_SYNC", f"pending={pending}")
        return Response({"server_time": int(timezone.now().timestamp()), "pending_commands": pending})


class StatusView(DeviceBase):
    def get(self, request):
        return Response(device_dict(request.user.device))


class RenewTokenView(DeviceBase):
    def post(self, request):
        device = request.user.device
        token = device.issue_token()
        device.save(update_fields=["auth_token_hash", "updated_at"])
        log_event(device, "CREDENTIAL_RENEWED")
        return Response({"device_token": token})


class OperatorBase(APIView):
    """Single operator (Django staff user). No role hierarchy."""
    def get_device(self, device_id) -> Device:
        return get_object_or_404(Device, pk=device_id)


class DeviceInfoView(OperatorBase):
    def get(self, request, device_id):
        device = self.get_device(device_id)
        data = device_dict(device)
        last = device.commands.first()
        data["last_command"] = None if not last else {
            "id": str(last.id), "type": last.command_type, "status": last.command_status,
            "result": last.execution_result}
        return Response(data)


class OperatorCommandView(OperatorBase):
    command_type = None

    def post(self, request, device_id):
        device = self.get_device(device_id)
        if device.enrollment_status == Device.Enrollment.RELEASED:
            return Response({"error": "device_released"}, status=status.HTTP_409_CONFLICT)
        expire_stale(device)
        existing = device.commands.filter(
            command_type=self.command_type,
            command_status__in=[DeviceCommand.Status.PENDING, DeviceCommand.Status.DELIVERED]).first()
        if existing:  # duplicate prevention
            return Response({"command_id": str(existing.id), "status": existing.command_status,
                             "duplicate": True})
        cmd = create_command(device, self.command_type, request.data.get("reason", ""),
                             request.data.get("ttl_seconds"))
        return Response({"command_id": str(cmd.id), "status": cmd.command_status,
                         "device_online": device.is_online}, status=status.HTTP_201_CREATED)


class LockView(OperatorCommandView):
    command_type = DeviceCommand.Type.LOCK


class UnlockView(OperatorCommandView):
    command_type = DeviceCommand.Type.UNLOCK


class ReleaseView(OperatorCommandView):
    command_type = DeviceCommand.Type.RELEASE


class SyncCommandView(OperatorCommandView):
    command_type = DeviceCommand.Type.SYNC
