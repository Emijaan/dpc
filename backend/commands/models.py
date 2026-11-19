import uuid

from django.db import models


class DeviceCommand(models.Model):
    class Type(models.TextChoices):
        LOCK = "DEVICE_LOCK"
        UNLOCK = "DEVICE_UNLOCK"
        STATUS = "DEVICE_STATUS"
        SYNC = "DEVICE_SYNC"
        RELEASE = "DEVICE_RELEASE"

    class Status(models.TextChoices):
        PENDING = "PENDING"      # stored, device has not fetched it
        DELIVERED = "DELIVERED"  # device fetched it
        EXECUTED = "EXECUTED"    # device reported success
        FAILED = "FAILED"        # device reported failure/rejection
        EXPIRED = "EXPIRED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey("devices.Device", on_delete=models.CASCADE, related_name="commands")
    command_type = models.CharField(max_length=20, choices=Type.choices)
    reason = models.CharField(max_length=200, blank=True)
    command_status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    issued_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    executed_at = models.DateTimeField(null=True, blank=True)
    execution_result = models.CharField(max_length=300, blank=True)
    nonce = models.CharField(max_length=64)
    signature = models.TextField(blank=True)

    class Meta:
        ordering = ["-issued_at"]
