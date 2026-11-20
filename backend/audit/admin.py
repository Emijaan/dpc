from django.contrib import admin

from audit.models import DeviceAuditLog


@admin.register(DeviceAuditLog)
class DeviceAuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "actor", "event", "source_ip", "client_device", "device", "result")
    list_filter = ("event",)
    search_fields = ("event", "result", "key_id", "source_ip", "client_device", "device__model", "actor__username")
    readonly_fields = ("timestamp", "actor", "device", "command", "key_id", "event", "result", "source_ip", "client_device", "user_agent")
