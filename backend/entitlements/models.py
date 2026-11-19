import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


def default_expiry():
    return timezone.now() + timedelta(days=365)


class EntitlementAllocation(models.Model):
    """Commercial device-registration entitlement allocation (365-day validity)."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        EXHAUSTED = "EXHAUSTED"
        EXPIRED = "EXPIRED"
        DISABLED = "DISABLED"
        CANCELLED = "CANCELLED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    allocated_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="received_allocations"
    )
    allocated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="issued_allocations"
    )
    parent_allocation = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="child_allocations"
    )
    allocated_quantity = models.PositiveIntegerField()
    distributed_quantity = models.PositiveIntegerField(default=0)
    consumed_quantity = models.PositiveIntegerField(default=0)
    available_quantity = models.PositiveIntegerField()
    issued_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(default=default_expiry)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issued_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    allocated_quantity=F("distributed_quantity") + F("consumed_quantity") + F("available_quantity")
                ),
                name="entitlement_balance_equation",
            ),
        ]

    def clean(self):
        if self.allocated_quantity < 1:
            raise ValidationError("allocated_quantity must be at least 1.")
        if self.distributed_quantity + self.consumed_quantity + self.available_quantity != self.allocated_quantity:
            raise ValidationError("Allocation quantities do not balance.")

    def compute_status(self, now=None) -> str:
        if self.status in (self.Status.CANCELLED, self.Status.DISABLED):
            return self.status
        now = now or timezone.now()
        if self.expires_at <= now:
            return self.Status.EXPIRED
        if self.available_quantity == 0:
            return self.Status.EXHAUSTED
        return self.Status.ACTIVE

    def __str__(self):
        return f"{self.allocated_to.username}: {self.available_quantity}/{self.allocated_quantity} ({self.status})"


class EntitlementTransfer(models.Model):
    class Status(models.TextChoices):
        COMPLETED = "COMPLETED"
        REJECTED = "REJECTED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sent_entitlement_transfers"
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="received_entitlement_transfers"
    )
    source_allocation = models.ForeignKey(
        EntitlementAllocation, on_delete=models.PROTECT, related_name="outgoing_transfers"
    )
    target_allocation = models.ForeignKey(
        EntitlementAllocation, null=True, blank=True, on_delete=models.PROTECT, related_name="incoming_transfers"
    )
    quantity = models.PositiveIntegerField()
    transferred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="performed_entitlement_transfers"
    )
    transfer_date = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=300, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.COMPLETED)

    class Meta:
        ordering = ["-transfer_date"]


class EntitlementConsumption(models.Model):
    """Append-only ledger recording permanent entitlement consumption per registered device."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    allocation = models.ForeignKey(
        EntitlementAllocation, on_delete=models.PROTECT, related_name="consumptions"
    )
    device = models.OneToOneField(
        "devices.Device", on_delete=models.PROTECT, related_name="entitlement_consumption"
    )
    retailer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="retailer_consumptions"
    )
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="vendor_consumptions"
    )
    consumed_at = models.DateTimeField(auto_now_add=True)
    registration_reference = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["-consumed_at"]

    def delete(self, *args, **kwargs):
        raise ValidationError("EntitlementConsumption records are append-only and cannot be deleted.")
