import uuid

from django.conf import settings
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
    key_id = models.CharField(max_length=64, blank=True, default="")
    signature = models.TextField(blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="issued_commands",
    )
    enrollment_session = models.ForeignKey(
        "devices.EnrollmentSession",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commands",
    )
    retailer_id_snapshot = models.IntegerField(null=True, blank=True)
    vendor_id_snapshot = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_at"]
