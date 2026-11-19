from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class DeviceAuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events"
    )
    device = models.ForeignKey("devices.Device", null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs")
    command = models.ForeignKey("commands.DeviceCommand", null=True, blank=True, on_delete=models.SET_NULL)
    key_id = models.CharField(max_length=64, blank=True, default="")
    target_type = models.CharField(max_length=32, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    retailer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="retailer_audit_logs"
    )
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="vendor_audit_logs"
    )
    event = models.CharField(max_length=60)
    result = models.CharField(max_length=300, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit logs are append-only and cannot be deleted.")


def client_ip(request) -> str | None:
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_event(
    device,
    event,
    result="",
    command=None,
    actor=None,
    key_id="",
    source_ip=None,
    request=None,
    target_type="",
    target_id="",
):
    ip = source_ip or client_ip(request)
    user = actor
    if user is None and request is not None and getattr(request, "user", None) is not None:
        if getattr(request.user, "is_authenticated", False) and hasattr(request.user, "pk"):
            from django.contrib.auth import get_user_model
            if isinstance(request.user, get_user_model()):
                user = request.user
    retailer = getattr(device, "retailer", None) if device is not None else None
    vendor = getattr(device, "vendor", None) if device is not None else None
    if retailer is None and user is not None:
        prof = getattr(user, "profile", None)
        if prof is not None:
            if prof.account_type == "RETAILER":
                retailer = user
            elif prof.account_type == "VENDOR":
                retailer = prof.retailer
                vendor = user
    return DeviceAuditLog.objects.create(
        actor=user,
        device=device,
        command=command,
        key_id=str(key_id or ""),
        target_type=str(target_type or ("device" if device is not None else "")),
        target_id=str(target_id or (device.id if device is not None else "")),
        retailer=retailer,
        vendor=vendor,
        event=event,
        result=str(result)[:300],
        source_ip=ip,
    )
