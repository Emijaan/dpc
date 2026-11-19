from django.contrib import admin

from entitlements.models import EntitlementAllocation, EntitlementConsumption, EntitlementTransfer


@admin.register(EntitlementAllocation)
class EntitlementAllocationAdmin(admin.ModelAdmin):
    list_display = (
        "allocated_to", "allocated_by", "allocated_quantity",
        "distributed_quantity", "consumed_quantity", "available_quantity", "status", "expires_at",
    )
    list_filter = ("status",)


@admin.register(EntitlementTransfer)
class EntitlementTransferAdmin(admin.ModelAdmin):
    list_display = ("sender", "receiver", "quantity", "transferred_by", "status", "transfer_date")
    list_filter = ("status",)


@admin.register(EntitlementConsumption)
class EntitlementConsumptionAdmin(admin.ModelAdmin):
    list_display = ("device", "allocation", "retailer", "vendor", "registration_reference", "consumed_at")
