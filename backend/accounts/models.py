import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F


class AccountProfile(models.Model):
    """Defines tenant hierarchy: SUPERUSER -> RETAILER -> VENDOR."""

    class AccountType(models.TextChoices):
        SUPERUSER = "SUPERUSER"
        RETAILER = "RETAILER"
        VENDOR = "VENDOR"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    account_type = models.CharField(
        max_length=16, choices=AccountType.choices, default=AccountType.VENDOR
    )
    retailer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="vendor_profiles",
    )
    entitlement_quota = models.PositiveIntegerField(null=True, blank=True)
    entitlements_consumed = models.PositiveIntegerField(default=0)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    last_device = models.CharField(max_length=128, blank=True, default="")
    last_user_agent = models.CharField(max_length=255, blank=True, default="")
    last_active_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user_id"]

    def clean(self):
        if self.account_type == self.AccountType.VENDOR:
            if not self.retailer_id:
                raise ValidationError("A VENDOR account must belong to a RETAILER.")
            if self.retailer_id == self.user_id:
                raise ValidationError("A VENDOR cannot be its own RETAILER.")
            ret_profile = getattr(self.retailer, "profile", None)
            if not ret_profile or ret_profile.account_type != self.AccountType.RETAILER:
                raise ValidationError("Assigned retailer must have account_type=RETAILER.")
        elif self.account_type in (self.AccountType.RETAILER, self.AccountType.SUPERUSER):
            if self.retailer_id is not None:
                raise ValidationError(f"{self.account_type} cannot have a parent retailer.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def effective_retailer_id(self):
        if self.account_type == self.AccountType.RETAILER:
            return self.user_id
        if self.account_type == self.AccountType.VENDOR:
            return self.retailer_id
        return None

    def __str__(self):
        return f"{self.user.username} ({self.account_type})"


def get_or_create_profile(user) -> AccountProfile | None:
    if not user or not getattr(user, "is_authenticated", False):
        return None
    profile = getattr(user, "profile", None)
    if profile is not None:
        return profile
    if getattr(user, "is_superuser", False):
        profile, _ = AccountProfile.objects.get_or_create(
            user=user, defaults={"account_type": AccountProfile.AccountType.SUPERUSER}
        )
        return profile
    return None


def consume_entitlement(user) -> bool:
    """Atomically increments entitlements_consumed; never restored on release/transfer."""
    if not user:
        return True
    with transaction.atomic():
        profile = AccountProfile.objects.select_for_update().filter(user=user).first()
        if profile is None:
            return True
        if profile.entitlement_quota is not None and profile.entitlements_consumed >= profile.entitlement_quota:
            return False
        AccountProfile.objects.filter(pk=profile.pk).update(
            entitlements_consumed=F("entitlements_consumed") + 1
        )
        return True


class TenantStatus(models.TextChoices):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Retailer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="retailer_profile"
    )
    full_name = models.CharField(max_length=128, blank=True, default="")
    business_name = models.CharField(max_length=160)
    contact_person = models.CharField(max_length=128, blank=True, default="")
    address = models.TextField(blank=True, default="")
    mobile = models.CharField(max_length=32, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    status = models.CharField(max_length=16, choices=TenantStatus.choices, default=TenantStatus.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.business_name} ({self.account.username})"


class Vendor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vendor_profile"
    )
    retailer = models.ForeignKey(Retailer, on_delete=models.PROTECT, related_name="vendors")
    full_name = models.CharField(max_length=128, blank=True, default="")
    business_name = models.CharField(max_length=160)
    contact_person = models.CharField(max_length=128, blank=True, default="")
    address = models.TextField(blank=True, default="")
    mobile = models.CharField(max_length=32, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    status = models.CharField(max_length=16, choices=TenantStatus.choices, default=TenantStatus.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.account_id and self.retailer_id and self.account_id == self.retailer.account_id:
            raise ValidationError("Vendor cannot belong to itself as retailer.")

    def __str__(self):
        return f"{self.business_name} ({self.account.username})"
