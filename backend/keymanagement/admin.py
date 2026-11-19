from django.contrib import admin

from keymanagement.models import DevicePublicKey, SigningKey


@admin.register(SigningKey)
class SigningKeyAdmin(admin.ModelAdmin):
    list_display = ("id", "category", "version", "algorithm", "status", "activated_at", "expires_at", "revoked_at")
    list_filter = ("category", "status")
    readonly_fields = ("id", "public_key_pem", "public_key_b64", "private_key_ref", "created_at")


@admin.register(DevicePublicKey)
class DevicePublicKeyAdmin(admin.ModelAdmin):
    list_display = ("key_id", "device", "version", "algorithm", "status", "registered_at")
    list_filter = ("status", "algorithm")
    readonly_fields = ("id", "public_key_b64", "registered_at")
