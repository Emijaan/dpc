from django.contrib import admin

from devices.models import Customer, Device, DeviceOwnershipTransfer, EnrollmentSession


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "retailer", "vendor", "created_at")
    search_fields = ("full_name",)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        "device_identifier",
        "model",
        "retailer",
        "vendor",
        "ownership_status",
        "enrollment_status",
        "restriction_status",
        "last_seen",
    )
    list_filter = ("ownership_status", "enrollment_status", "restriction_status")
    search_fields = ("device_identifier", "model")


@admin.register(EnrollmentSession)
class EnrollmentSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "retailer", "vendor", "status", "expires_at", "created_at")
    list_filter = ("status",)


@admin.register(DeviceOwnershipTransfer)
class DeviceOwnershipTransferAdmin(admin.ModelAdmin):
    list_display = ("device", "from_retailer", "from_vendor", "to_retailer", "to_vendor", "transferred_by", "transferred_at")
