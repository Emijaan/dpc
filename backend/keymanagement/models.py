import uuid

from django.db import models


class SigningKey(models.Model):
    class Category(models.TextChoices):
        ROOT = "ROOT"
        COMMAND = "COMMAND"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        ROTATED = "ROTATED"
        REVOKED = "REVOKED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.COMMAND)
    algorithm = models.CharField(max_length=32, default="ECDSA_P256")
    version = models.PositiveIntegerField(default=1)
    public_key_pem = models.TextField()
    public_key_b64 = models.TextField()
    # Filesystem / KMS reference only — never store plaintext private keys in PostgreSQL.
    private_key_ref = models.CharField(max_length=512, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    activated_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version", "-created_at"]

    def __str__(self):
        return f"{self.category} v{self.version} ({self.id}) [{self.status}]"


class DevicePublicKey(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        REVOKED = "REVOKED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey("devices.Device", on_delete=models.CASCADE, related_name="public_keys")
    key_id = models.CharField(max_length=64)
    algorithm = models.CharField(max_length=32, default="ECDSA_P256")
    public_key_b64 = models.TextField()
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    registered_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-version", "-registered_at"]
