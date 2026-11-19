from django.contrib import admin

from commands.models import DeviceCommand


@admin.register(DeviceCommand)
class DeviceCommandAdmin(admin.ModelAdmin):
    list_display = ("command_type", "device", "command_status", "issued_at", "expires_at", "executed_at")
    list_filter = ("command_type", "command_status")
    search_fields = ("id", "device__model", "device__device_identifier")
    readonly_fields = ("id", "nonce", "signature", "issued_at", "executed_at")
