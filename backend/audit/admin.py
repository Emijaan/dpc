from django.contrib import admin

from audit.models import DeviceAuditLog


@admin.register(DeviceAuditLog)
class DeviceAuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "event", "device", "command", "result")
    list_filter = ("event",)
    search_fields = ("event", "result", "device__model")
    readonly_fields = ("timestamp", "device", "command", "event", "result")
