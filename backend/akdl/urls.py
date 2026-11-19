from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView

from devices import panel


def api_docs(request):
    """Self-describing REST API documentation endpoint."""
    return JsonResponse({
        "service": "AK DeviceLock REST API v1",
        "authentication": {
            "device_registration": "Header X-Enrollment-Key",
            "device_endpoints": "Header Authorization: Device <device_token>",
            "operator_endpoints": "RBAC-authorized Staff Session or BasicAuth",
        },
        "endpoints": [
            {"method": "POST", "path": "/api/v1/devices/register/", "auth": "X-Enrollment-Key"},
            {"method": "POST", "path": "/api/v1/devices/sync/", "auth": "Device"},
            {"method": "GET", "path": "/api/v1/devices/status/", "auth": "Device"},
            {"method": "POST", "path": "/api/v1/devices/renew-token/", "auth": "Device"},
            {"method": "GET", "path": "/api/v1/commands/pending/", "auth": "Device"},
            {"method": "POST", "path": "/api/v1/commands/acknowledge/", "auth": "Device"},
            {"method": "GET", "path": "/api/v1/devices/{device_id}/", "auth": "RBAC: devices.view"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/lock/", "auth": "RBAC: devices.lock"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/unlock/", "auth": "RBAC: devices.unlock"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/release/", "auth": "RBAC: devices.release"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/keys/register/", "auth": "Device or keys.manage"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/keys/renew/", "auth": "Device or keys.manage"},
            {"method": "GET/POST", "path": "/api/v1/roles/", "auth": "RBAC: roles.manage"},
            {"method": "PUT/DELETE", "path": "/api/v1/roles/{role_id}/", "auth": "RBAC: roles.manage"},
            {"method": "POST", "path": "/api/v1/roles/{role_id}/permissions/", "auth": "RBAC: roles.manage"},
            {"method": "GET/POST", "path": "/api/v1/accounts/", "auth": "RBAC: accounts.manage"},
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
    path("admin/", admin.site.urls),
    path("panel/", panel.panel_home, name="panel"),
    path("panel/qr/", panel.panel_qr, name="panel_qr"),
    path("panel/rbac/role/", panel.panel_create_role, name="panel_create_role"),
    path("panel/rbac/assign/", panel.panel_assign_role, name="panel_assign_role"),
    path("panel/rbac/account/", panel.panel_create_account, name="panel_create_account"),
    path("panel/keys/<str:action>/", panel.panel_key_action, name="panel_key_action"),
    path("panel/<uuid:device_id>/<str:action>/", panel.panel_action, name="panel_action"),
    path("download/akdevicelock.apk", panel.download_apk, name="download_apk"),
    path("download/testdpc.apk", panel.download_testdpc_apk, name="download_testdpc_apk"),
    path("api/v1/docs/", api_docs, name="api_docs"),
    path("api/v1/roles/", include("roles.urls")),
    path("api/v1/accounts/", include("accounts.urls")),
    path("api/v1/keys/", include("keymanagement.urls")),
    path("api/v1/devices/", include("devices.urls")),
    path("api/v1/commands/", include("commands.urls")),
]
