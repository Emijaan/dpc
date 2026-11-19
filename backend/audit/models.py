from django.db import models


class DeviceAuditLog(models.Model):
    device = models.ForeignKey("devices.Device", null=True, on_delete=models.SET_NULL, related_name="audit_logs")
    command = models.ForeignKey("commands.DeviceCommand", null=True, blank=True, on_delete=models.SET_NULL)
    event = models.CharField(max_length=60)
    result = models.CharField(max_length=300, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]


def log_event(device, event, result="", command=None):
    return DeviceAuditLog.objects.create(device=device, command=command, event=event, result=result[:300])
