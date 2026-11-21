from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView


def favicon_view(request):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><text y="52" font-size="52">🛡️</text></svg>'
    return HttpResponse(svg, content_type="image/svg+xml")

from accounts.auth_views import HealthView as AuthHealth
from devices import panel, views as device_views


def api_docs(request):
    """Self-describing REST API documentation endpoint."""
    return JsonResponse({
        "service": "AK DeviceLock REST API v1",
        "authentication": {
            "device_registration": "Header X-Enrollment-Key",
            "device_endpoints": "Header Authorization: Device <device_token>",
            "operator_endpoints": "Authorization: Bearer <JWT access token> (obtain via /api/v1/auth/login/) or staff session",
        },
        "endpoints": [
            {"method": "POST", "path": "/api/v1/auth/login/", "auth": "none (rate-limited)"},
            {"method": "POST", "path": "/api/v1/auth/refresh/", "auth": "refresh token (rotates; old one blacklisted)"},
            {"method": "POST", "path": "/api/v1/auth/logout/", "auth": "Bearer + refresh token in body"},
            {"method": "GET", "path": "/api/v1/auth/me/", "auth": "Bearer"},
            {"method": "GET", "path": "/api/v1/health/", "auth": "none"},
            {"method": "POST", "path": "/api/v1/devices/register/", "auth": "X-Enrollment-Key"},
            {"method": "POST", "path": "/api/v1/devices/sync/", "auth": "Device"},
            {"method": "POST", "path": "/api/v1/devices/photo/", "auth": "Device"},
            {"method": "GET", "path": "/api/v1/devices/status/", "auth": "Device"},
            {"method": "POST", "path": "/api/v1/devices/renew-token/", "auth": "Device"},
            {"method": "GET", "path": "/api/v1/commands/pending/", "auth": "Device"},
            {"method": "POST", "path": "/api/v1/commands/acknowledge/", "auth": "Device"},
            {"method": "GET", "path": "/api/v1/devices/{device_id}/", "auth": "RBAC: devices.view"},
            {"method": "GET", "path": "/api/v1/devices/{device_id}/photo/", "auth": "RBAC: devices.view"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/lock/", "auth": "RBAC: devices.lock"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/unlock/", "auth": "RBAC: devices.unlock"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/locate/", "auth": "RBAC: devices.sync"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/capture-photo/", "auth": "RBAC: devices.lock"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/camera/", "auth": "RBAC: devices.lock"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/gps-policy/", "auth": "RBAC: devices.lock"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/network-policy/", "auth": "RBAC: devices.lock"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/update-agent/", "auth": "RBAC: devices.lock"},
            {"method": "GET/PUT", "path": "/api/v1/devices/frp-policy/", "auth": "Superuser / RBAC: devices.view"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/release/", "auth": "RBAC: devices.release"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/keys/register/", "auth": "Device or keys.manage"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/keys/renew/", "auth": "Device or keys.manage"},
            {"method": "GET/POST", "path": "/api/v1/roles/", "auth": "RBAC: roles.manage"},
            {"method": "PUT/DELETE", "path": "/api/v1/roles/{role_id}/", "auth": "RBAC: roles.manage"},
            {"method": "POST", "path": "/api/v1/roles/{role_id}/permissions/", "auth": "RBAC: roles.manage"},
            {"method": "GET/POST", "path": "/api/v1/accounts/", "auth": "RBAC: accounts.manage"},
            {"method": "GET/PATCH/DELETE", "path": "/api/v1/accounts/{account_id}/", "auth": "RBAC: accounts.manage"},
            {"method": "POST", "path": "/api/v1/accounts/{account_id}/activate/", "auth": "RBAC: accounts.manage"},
            {"method": "POST", "path": "/api/v1/accounts/{account_id}/deactivate/", "auth": "RBAC: accounts.manage"},
            {"method": "GET/POST", "path": "/api/v1/retailers/", "auth": "RBAC: accounts.manage (Superuser create)"},
            {"method": "GET/PATCH", "path": "/api/v1/retailers/{retailer_id}/", "auth": "RBAC: accounts.manage"},
            {"method": "GET/POST", "path": "/api/v1/vendors/", "auth": "RBAC: accounts.manage"},
            {"method": "GET/PATCH", "path": "/api/v1/vendors/{vendor_id}/", "auth": "RBAC: accounts.manage"},
            {"method": "POST", "path": "/api/v1/entitlements/allocate/", "auth": "Bearer/Session (Superuser or Retailer)"},
            {"method": "POST", "path": "/api/v1/entitlements/transfer/", "auth": "Bearer/Session (Vendor/Retailer/Superuser)"},
            {"method": "GET", "path": "/api/v1/entitlements/", "auth": "Bearer/Session"},
            {"method": "GET", "path": "/api/v1/entitlements/balance/", "auth": "Bearer/Session"},
            {"method": "GET", "path": "/api/v1/entitlements/history/", "auth": "Bearer/Session"},
            {"method": "GET", "path": "/api/v1/entitlements/consumption/", "auth": "Bearer/Session"},
            {"method": "POST", "path": "/api/v1/accounts/{account_id}/roles/", "auth": "RBAC: roles.manage"},
            {"method": "GET", "path": "/api/v1/keys/", "auth": "RBAC: keys.view"},
            {"method": "GET", "path": "/api/v1/keys/public/", "auth": "Device"},
            {"method": "POST", "path": "/api/v1/keys/generate/", "auth": "RBAC: keys.manage"},
            {"method": "POST", "path": "/api/v1/keys/rotate/", "auth": "RBAC: keys.manage"},
            {"method": "POST", "path": "/api/v1/keys/{key_id}/revoke/", "auth": "RBAC: keys.manage"},
            {"method": "GET", "path": "/api/v1/keys/{key_id}/", "auth": "RBAC: keys.view"},
        ],
    })


urlpatterns = [
    path("", RedirectView.as_view(pattern_name="panel", permanent=False)),
    path("favicon.ico", favicon_view),
    path("admin/", admin.site.urls),
    path("panel/", panel.panel_home, name="panel"),
    path("panel/qr/", panel.panel_qr, name="panel_qr"),
    path("panel/rbac/role/", panel.panel_create_role, name="panel_create_role"),
    path("panel/rbac/assign/", panel.panel_assign_role, name="panel_assign_role"),
    path("panel/rbac/account/", panel.panel_create_account, name="panel_create_account"),
    path("panel/accounts/<int:account_id>/quota/", panel.panel_set_quota, name="panel_set_quota"),
    path("panel/accounts/<int:account_id>/toggle/", panel.panel_toggle_account, name="panel_toggle_account"),
    path("panel/accounts/<int:account_id>/delete/", panel.panel_delete_account, name="panel_delete_account"),
    path("panel/enrollments/create/", panel.panel_create_enrollment, name="panel_create_enrollment"),
    path("panel/keys/<str:action>/", panel.panel_key_action, name="panel_key_action"),
    path("panel/<uuid:device_id>/<str:action>/", panel.panel_action, name="panel_action"),
    path("download/akdevicelock.apk", panel.download_apk, name="download_apk"),
    path("download/testdpc.apk", panel.download_testdpc_apk, name="download_testdpc_apk"),
    path("api/v1/docs/", api_docs, name="api_docs"),
    path("api/v1/health/", AuthHealth.as_view(), name="api_health"),
    path("api/v1/auth/", include("accounts.auth_urls")),
    path("api/v1/roles/", include("roles.urls")),
    path("api/v1/accounts/", include("accounts.urls")),
    path("api/v1/retailers/", include("accounts.retailer_urls")),
    path("api/v1/vendors/", include("accounts.vendor_urls")),
    path("api/v1/entitlements/", include("entitlements.urls")),
    path("api/v1/keys/", include("keymanagement.urls")),
    path("api/v1/dashboard/stats/", device_views.DashboardStatsView.as_view()),
    path("api/v1/registrations/", device_views.RegistrationCreateView.as_view()),
    path("api/v1/devices/", include("devices.urls")),
    path("api/v1/commands/", include("commands.urls")),
    path("api/v1/customers/", device_views.CustomerListCreateView.as_view()),
    path("api/v1/customers/<uuid:customer_id>/", device_views.CustomerDetailView.as_view()),
    path("api/v1/customers/<uuid:customer_id>/reveal/", device_views.CustomerRevealView.as_view()),
    path("api/v1/enrollment/", include("devices.enrollment_urls")),
    path("api/v1/enrollments/", device_views.EnrollmentListCreateView.as_view()),
    path("api/v1/enrollments/<uuid:session_id>/", device_views.EnrollmentDetailView.as_view()),
    path("api/v1/enrollments/<uuid:session_id>/qr/", device_views.EnrollmentQRView.as_view()),
    path("api/v1/enrollments/<uuid:session_id>/provision-bat/", device_views.EnrollmentBatView.as_view()),
    path("api/v1/audit/", device_views.AuditHistoryView.as_view()),
]
