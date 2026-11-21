from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response

from audit.models import log_event
from commands.models import DeviceCommand
from commands.services import expire_stale
from devices.models import Device, effective_frp_accounts
from devices.views import DeviceBase


def command_payload(c: DeviceCommand) -> dict:
    return {
        "command_id": str(c.id), "device_id": str(c.device_id), "command_type": c.command_type,
        "issued_at": int(c.issued_at.timestamp()), "expires_at": int(c.expires_at.timestamp()),
        "nonce": c.nonce, "key_id": c.key_id, "signature": c.signature, "reason": c.reason,
    }


class PendingView(DeviceBase):
    def get(self, request):
        device = request.user.device
        device.touch()
        device.save()
        expire_stale(device)
        cmds = list(device.commands.filter(
            command_status__in=[DeviceCommand.Status.PENDING, DeviceCommand.Status.DELIVERED]
        ).order_by("issued_at"))
        for c in cmds:
            if c.command_status == DeviceCommand.Status.PENDING:
                c.command_status = DeviceCommand.Status.DELIVERED
                c.save(update_fields=["command_status"])
                log_event(device, "COMMAND_DELIVERED", c.command_type, c)
        return Response({
            "server_time": int(timezone.now().timestamp()),
            "commands": [command_payload(c) for c in cmds],
            "lock_screen": device.lock_screen_info(),
            "frp_accounts": effective_frp_accounts(device),
        })


class AckSerializer(serializers.Serializer):
    command_id = serializers.UUIDField()
    success = serializers.BooleanField()
    result = serializers.CharField(max_length=300, allow_blank=True, required=False, default="")


class AcknowledgeView(DeviceBase):
    def post(self, request):
        device = request.user.device
        s = AckSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        cmd = device.commands.filter(pk=d["command_id"]).first()
        if cmd is None:
            return Response({"error": "unknown_command"}, status=status.HTTP_404_NOT_FOUND)
        if cmd.command_status in (DeviceCommand.Status.EXECUTED, DeviceCommand.Status.FAILED):
            return Response({"status": cmd.command_status, "duplicate": True})  # idempotent
        if d["success"]:
            cmd.command_status = DeviceCommand.Status.EXECUTED
            if cmd.command_type == DeviceCommand.Type.LOCK:
                device.restriction_status = Device.Restriction.LOCKED
            elif cmd.command_type == DeviceCommand.Type.UNLOCK:
                device.restriction_status = Device.Restriction.NONE
            elif cmd.command_type == DeviceCommand.Type.CAMERA_DISABLE:
                device.camera_disabled = True
            elif cmd.command_type == DeviceCommand.Type.CAMERA_ENABLE:
                device.camera_disabled = False
            elif cmd.command_type == DeviceCommand.Type.GPS_FORCE_ON:
                device.gps_forced_on = True
            elif cmd.command_type == DeviceCommand.Type.GPS_UNLOCK:
                device.gps_forced_on = False
            elif cmd.command_type == DeviceCommand.Type.NETWORK_RESTRICT:
                device.network_restricted = True
            elif cmd.command_type == DeviceCommand.Type.NETWORK_ALLOW:
                device.network_restricted = False
            elif cmd.command_type == DeviceCommand.Type.RELEASE:
                device.restriction_status = Device.Restriction.NONE
                device.enrollment_status = Device.Enrollment.RELEASED
                device.ownership_status = Device.OwnershipStatus.RELEASED
                if not device.released_at:
                    device.released_at = timezone.now()
        else:
            cmd.command_status = DeviceCommand.Status.FAILED
            if cmd.command_type == DeviceCommand.Type.LOCK and device.restriction_status == Device.Restriction.LOCK_PENDING:
                device.restriction_status = Device.Restriction.NONE
            elif cmd.command_type in (DeviceCommand.Type.UNLOCK, DeviceCommand.Type.RELEASE):
                if device.restriction_status in (Device.Restriction.UNLOCK_PENDING, Device.Restriction.RELEASE_PENDING):
                    device.restriction_status = Device.Restriction.LOCKED
        cmd.executed_at = timezone.now()
        cmd.execution_result = d["result"]
        cmd.save()
        device.touch()
        device.save()
        log_event(device, "COMMAND_ACK", f"{cmd.command_status}: {d['result']}", cmd)
        return Response({"status": cmd.command_status})
