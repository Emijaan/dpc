from django.contrib import admin

from devices.models import Device


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("model", "manufacturer", "android_version", "enrollment_status", "restriction_status", "last_seen")
    list_filter = ("enrollment_status", "restriction_status", "manufacturer")
    search_fields = ("device_identifier", "model", "manufacturer")
    readonly_fields = ("id", "auth_token_hash", "created_at", "updated_at")
