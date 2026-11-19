import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Device(models.Model):
    class Enrollment(models.TextChoices):
        ENROLLED = "ENROLLED"
        RELEASED = "RELEASED"

    class Restriction(models.TextChoices):
        NONE = "NONE"
        LOCKED = "LOCKED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device_identifier = models.CharField(max_length=64, unique=True)  # generated installation id
    manufacturer = models.CharField(max_length=64, blank=True)
    model = models.CharField(max_length=64, blank=True)
    android_version = models.CharField(max_length=16, blank=True)
    sdk_version = models.PositiveIntegerField(default=0)
    app_version = models.CharField(max_length=32, blank=True)
    fcm_token = models.CharField(max_length=512, blank=True)  # reserved; FCM not enabled yet
    enrollment_status = models.CharField(max_length=16, choices=Enrollment.choices, default=Enrollment.ENROLLED)
    connection_status = models.CharField(max_length=16, default="OFFLINE")
    restriction_status = models.CharField(max_length=16, choices=Restriction.choices, default=Restriction.NONE)
    last_seen = models.DateTimeField(null=True, blank=True)
    auth_token_hash = models.CharField(max_length=64, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.model} ({self.device_identifier})"

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def issue_token(self) -> str:
        """Create a new device credential. The plaintext is returned once and only the hash is stored."""
        token = secrets.token_urlsafe(32)
        self.auth_token_hash = self.hash_token(token)
        return token

    @property
    def is_online(self) -> bool:
        return bool(self.last_seen) and timezone.now() - self.last_seen < timedelta(seconds=settings.ONLINE_WINDOW_SECONDS)

    def touch(self):
        self.last_seen = timezone.now()
        self.connection_status = "ONLINE"
