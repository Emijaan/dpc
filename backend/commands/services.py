import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from audit.models import log_event
from commands import signing
from commands.models import DeviceCommand


def create_command(device, command_type, reason="", ttl=None, request=None):
    ttl = min(int(ttl or settings.DEFAULT_COMMAND_TTL), settings.MAX_COMMAND_TTL)
    now = timezone.now().replace(microsecond=0)
    actor = None
    if request is not None and getattr(request, "user", None) is not None:
        if getattr(request.user, "is_authenticated", False) and hasattr(request.user, "pk"):
            from django.contrib.auth import get_user_model
            if isinstance(request.user, get_user_model()):
                actor = request.user
    try:
        enroll_session = device.enrollment_session
    except Exception:
        enroll_session = None
    cmd = DeviceCommand(
        device=device, command_type=command_type, reason=reason[:200],
        issued_at=now, expires_at=now + timedelta(seconds=ttl), nonce=secrets.token_hex(16),
        issued_by=actor,
        enrollment_session=enroll_session,
        retailer_id_snapshot=device.retailer_id,
        vendor_id_snapshot=device.vendor_id,
    )
    cmd.signature = signing.sign_command(cmd)
    cmd.save()
    log_event(device, "COMMAND_CREATED", f"{command_type} ttl={ttl}s", cmd, key_id=cmd.key_id, request=request)
    return cmd


def expire_stale(device=None):
    qs = DeviceCommand.objects.filter(
        command_status__in=[DeviceCommand.Status.PENDING, DeviceCommand.Status.DELIVERED],
        expires_at__lte=timezone.now())
    if device:
        qs = qs.filter(device=device)
    for cmd in qs:
        cmd.command_status = DeviceCommand.Status.EXPIRED
        cmd.save(update_fields=["command_status"])
        log_event(cmd.device, "COMMAND_EXPIRED", cmd.command_type, cmd, key_id=cmd.key_id)
