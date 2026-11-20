from django.contrib import admin

from accounts.models import AccountProfile, Retailer, Vendor


@admin.register(AccountProfile)
class AccountProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user", "account_type", "retailer", "entitlement_quota",
        "entitlements_consumed", "last_ip", "last_device", "last_active_at",
    )
    list_filter = ("account_type",)
    search_fields = ("user__username", "retailer__username", "last_ip", "last_device")


@admin.register(Retailer)
class RetailerAdmin(admin.ModelAdmin):
    list_display = ("business_name", "account", "contact_person", "mobile", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("business_name", "account__username", "contact_person", "mobile")


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("business_name", "account", "retailer", "contact_person", "mobile", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("business_name", "account__username", "retailer__business_name", "mobile")
