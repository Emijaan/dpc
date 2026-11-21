import hashlib
import secrets
import string
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from devices.crypto import (
    decrypt_value,
    encrypt_value,
    hash_identifier,
    mask_email,
    mask_imei,
    mask_mobile,
)


class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=128)
    mobile_encrypted = models.TextField(blank=True, default="")
    mobile_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    email_encrypted = models.TextField(blank=True, default="")
    email_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    retailer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retailer_customers",
    )
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="vendor_customers",
    )
    registered_by_account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="registered_customers",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def set_mobile(self, mobile: str):
        val = (mobile or "").strip()
        self.mobile_encrypted = encrypt_value(val)
        self.mobile_hash = hash_identifier(val)

    def get_mobile(self) -> str:
        return decrypt_value(self.mobile_encrypted)

    def masked_mobile(self) -> str:
        return mask_mobile(self.get_mobile())

    def set_email(self, email: str):
        val = (email or "").strip().lower()
        self.email_encrypted = encrypt_value(val)
        self.email_hash = hash_identifier(val)

    def get_email(self) -> str:
        return decrypt_value(self.email_encrypted)

    def masked_email(self) -> str:
        return mask_email(self.get_email())

    def __str__(self):
        return f"{self.full_name} ({self.id})"


class Device(models.Model):
    class Enrollment(models.TextChoices):
        PENDING = "PENDING"
        FAILED = "FAILED"
        ENROLLED = "ENROLLED"
        RELEASED = "RELEASED"

    class Restriction(models.TextChoices):
        NONE = "NONE"
        LOCK_PENDING = "LOCK_PENDING"
        LOCKED = "LOCKED"
        UNLOCK_PENDING = "UNLOCK_PENDING"
        RELEASE_PENDING = "RELEASE_PENDING"

    class OwnershipStatus(models.TextChoices):
        ACTIVE = "ACTIVE"
        TRANSFERRED = "TRANSFERRED"
        RELEASED = "RELEASED"

    class EnrollmentMethod(models.TextChoices):
        QR_9_15 = "QR_9_15"
        ADB_16 = "ADB_16"
        DIRECT_QR = "DIRECT_QR"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device_identifier = models.CharField(max_length=64, unique=True)  # generated installation id
    registration_reference = models.CharField(max_length=32, blank=True, default="", db_index=True)
    imei_encrypted = models.TextField(blank=True, default="")
    imei_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    manufacturer = models.CharField(max_length=64, blank=True)
    model = models.CharField(max_length=64, blank=True)
    android_version = models.CharField(max_length=16, blank=True)
    sdk_version = models.PositiveIntegerField(default=0)
    app_version = models.CharField(max_length=32, blank=True)
    enrollment_method = models.CharField(
        max_length=16, choices=EnrollmentMethod.choices, default=EnrollmentMethod.QR_9_15
    )
    is_disabled = models.BooleanField(default=False)
    fcm_token = models.CharField(max_length=512, blank=True)  # reserved; FCM not enabled yet

    # Optional EMI & dealer/vendor display metadata shown on device lock screen
    emi_amount = models.CharField(max_length=32, blank=True, default="")
    emi_due_date = models.CharField(max_length=32, blank=True, default="")
    pending_emi_count = models.CharField(max_length=16, blank=True, default="")
    dealer_name = models.CharField(max_length=128, blank=True, default="")
    dealer_mobile = models.CharField(max_length=32, blank=True, default="")
    dealer_company = models.CharField(max_length=160, blank=True, default="")

    # Permanent ownership & tenant isolation associations
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.PROTECT, related_name="devices"
    )
    superuser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="platform_devices",
    )
    retailer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retailer_devices",
    )
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="vendor_devices",
    )
    original_retailer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="original_retailer_devices",
    )
    original_vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="original_vendor_devices",
    )
    registered_by_account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="registered_devices",
    )
    ownership_status = models.CharField(
        max_length=16, choices=OwnershipStatus.choices, default=OwnershipStatus.ACTIVE
    )

    enrollment_status = models.CharField(max_length=16, choices=Enrollment.choices, default=Enrollment.ENROLLED)
    connection_status = models.CharField(max_length=16, default="OFFLINE")
    restriction_status = models.CharField(max_length=16, choices=Restriction.choices, default=Restriction.NONE)
    registration_date = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    last_latitude = models.FloatField(null=True, blank=True)
    last_longitude = models.FloatField(null=True, blank=True)
    last_location_accuracy = models.FloatField(null=True, blank=True)
    last_location_at = models.DateTimeField(null=True, blank=True)
    network_type = models.CharField(max_length=32, blank=True, default="")
    wifi_ssid = models.CharField(max_length=64, blank=True, default="")
    network_operator = models.CharField(max_length=64, blank=True, default="")
    ip_address = models.CharField(max_length=64, blank=True, default="")
    camera_disabled = models.BooleanField(default=False)
    gps_forced_on = models.BooleanField(default=False)
    network_restricted = models.BooleanField(default=False)
    frp_accounts = models.CharField(max_length=256, blank=True, default="")
    last_photo_b64 = models.TextField(blank=True, default="")
    last_photo_at = models.DateTimeField(null=True, blank=True)
    auth_token_hash = models.CharField(max_length=64, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Ownership references that must never be silently reassigned.
    OWNERSHIP_FIELDS = (
        "customer_id", "superuser_id", "retailer_id", "vendor_id",
        "original_retailer_id", "original_vendor_id", "registered_by_account_id",
    )
    # Only these may change, and only through the Superuser transfer workflow.
    TRANSFERABLE_FIELDS = ("retailer_id", "vendor_id")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._owner_snapshot = {f: self.__dict__.get(f) for f in self.OWNERSHIP_FIELDS}
        self._transfer_authorized = False

    def clean(self):
        if self.vendor_id:
            if not self.retailer_id:
                raise ValidationError("A device with a vendor must also have a retailer.")
            v_profile = getattr(self.vendor, "profile", None)
            if v_profile and v_profile.retailer_id != self.retailer_id:
                raise ValidationError("Device vendor must belong to the device retailer.")

    def save(self, *args, **kwargs):
        if not self._state.adding:
            for f in self.OWNERSHIP_FIELDS:
                old = self._owner_snapshot.get(f)
                new = getattr(self, f)
                if new == old:
                    continue
                if f in self.TRANSFERABLE_FIELDS and self._transfer_authorized:
                    continue
                if f not in self.TRANSFERABLE_FIELDS and old is None:
                    continue  # first-time fill of a historical/original reference
                raise ValidationError(
                    f"Device ownership field '{f}' is immutable; use the Superuser transfer workflow."
                )
        self.clean()
        super().save(*args, **kwargs)
        self._owner_snapshot = {f: getattr(self, f) for f in self.OWNERSHIP_FIELDS}
        self._transfer_authorized = False

    def set_imei(self, imei: str):
        val = (imei or "").strip()
        self.imei_encrypted = encrypt_value(val)
        self.imei_hash = hash_identifier(val)

    def get_imei(self) -> str:
        return decrypt_value(self.imei_encrypted)

    def masked_imei(self) -> str:
        return mask_imei(self.get_imei())

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

    def lock_screen_info(self) -> dict:
        """Return optional EMI and dealer/vendor contact metadata for the Android lock screen."""
        return {
            "emi_amount": (self.emi_amount or "").strip(),
            "emi_due_date": (self.emi_due_date or "").strip(),
            "pending_emi_count": (self.pending_emi_count or "").strip(),
            "dealer_name": (self.dealer_name or "").strip(),
            "dealer_mobile": (self.dealer_mobile or "").strip(),
            "dealer_company": (self.dealer_company or "").strip(),
        }


class EnrollmentSession(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        USED = "USED"
        EXPIRED = "EXPIRED"
        REVOKED = "REVOKED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token_hash = models.CharField(max_length=64, unique=True)
    # Encrypted copy of the raw token so authorized owners can re-open the QR until the session is used/expired.
    # Cleared as soon as the session is consumed, expired, or revoked.
    token_encrypted = models.TextField(blank=True, default="", editable=False)
    superuser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="platform_enrollments",
    )
    retailer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retailer_enrollments",
    )
    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="vendor_enrollments",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_enrollments",
    )
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.PROTECT, related_name="enrollment_sessions"
    )
    intended_device_identifier = models.CharField(max_length=64, blank=True, default="")
    enrollment_method = models.CharField(
        max_length=16, choices=Device.EnrollmentMethod.choices, default=Device.EnrollmentMethod.QR_9_15
    )
    registration_reference = models.CharField(max_length=32, blank=True, default="")
    pending_device = models.ForeignKey(
        Device, null=True, blank=True, on_delete=models.SET_NULL, related_name="pending_enrollment_sessions"
    )
    registered_device = models.OneToOneField(
        Device, null=True, blank=True, on_delete=models.SET_NULL, related_name="enrollment_session"
    )
    entitlement_allocated = models.BooleanField(default=True)
    test_dpc_step_completed = models.BooleanField(default=False)
    ak_qr_generated = models.BooleanField(default=False)
    bat_downloaded = models.BooleanField(default=False)
    failure_reason = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_token() -> str:
        """Generate a 10-digit numeric enrollment key."""
        return "".join(secrets.choice(string.digits) for _ in range(10))

    @classmethod
    def create_session(
        cls,
        *,
        created_by,
        superuser=None,
        retailer=None,
        vendor=None,
        customer=None,
        intended_device_identifier="",
        enrollment_method=Device.EnrollmentMethod.QR_9_15,
        registration_reference="",
        pending_device=None,
        ttl_seconds: int = 900,
    ) -> tuple["EnrollmentSession", str]:
        while True:
            raw_token = cls.generate_token()
            token_hash = cls.hash_token(raw_token)
            if not cls.objects.filter(token_hash=token_hash).exists():
                break
        session = cls.objects.create(
            token_hash=token_hash,
            token_encrypted=encrypt_value(raw_token),
            superuser=superuser,
            retailer=retailer,
            vendor=vendor,
            created_by=created_by,
            customer=customer,
            intended_device_identifier=intended_device_identifier,
            enrollment_method=enrollment_method,
            registration_reference=registration_reference,
            pending_device=pending_device,
            expires_at=timezone.now() + timedelta(seconds=max(60, min(ttl_seconds, 86400))),
        )
        return session, raw_token

    @property
    def is_usable(self) -> bool:
        return self.status == self.Status.PENDING and self.expires_at > timezone.now()

    def get_raw_token(self) -> str:
        """Raw token for QR rendering; empty once used/expired/revoked."""
        if not self.is_usable:
            return ""
        return decrypt_value(self.token_encrypted)


class DeviceOwnershipTransfer(models.Model):
    """Immutable audit trail for Superuser-authorized device ownership transfers."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="ownership_transfers")
    from_retailer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transfers_from_retailer",
    )
    from_vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transfers_from_vendor",
    )
    to_retailer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transfers_to_retailer",
    )
    to_vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transfers_to_vendor",
    )
    transferred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="performed_device_transfers",
    )
    reason = models.CharField(max_length=300)
    transferred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-transferred_at"]


def parse_frp_ids(raw: str | list[str]) -> list[str]:
    import re
    if isinstance(raw, list):
        tokens = [str(x).strip() for x in raw]
    else:
        tokens = [t.strip() for t in re.split(r"[\s,;]+", raw or "") if t.strip()]
    seen: list[str] = []
    for t in tokens:
        if not re.fullmatch(r"\d{21}", t):
            raise ValidationError(
                f"Invalid Google Account ID '{t}'. Enterprise FRP requires 21-digit numeric Google Account IDs (not email addresses)."
            )
        if t not in seen:
            seen.append(t)
    return seen


class GlobalFrpSetting(models.Model):
    """Singleton platform-wide Enterprise Factory Reset Protection (Android 11+) Google Account IDs."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    account_ids_csv = models.CharField(max_length=512, blank=True, default="")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    updated_at = models.DateTimeField(auto_now=True)


def effective_frp_accounts(device: Device | None = None) -> list[str]:
    if device is not None and (device.frp_accounts or "").strip():
        try:
            return parse_frp_ids(device.frp_accounts)
        except ValidationError:
            pass
    try:
        cfg = GlobalFrpSetting.objects.filter(pk=1).first()
        if cfg and cfg.account_ids_csv.strip():
            return parse_frp_ids(cfg.account_ids_csv)
    except Exception:
        pass
    env_ids = getattr(settings, "FRP_ACCOUNT_IDS", []) or []
    try:
        return parse_frp_ids(list(env_ids))
    except ValidationError:
        return []
