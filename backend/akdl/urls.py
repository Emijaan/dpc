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
            "operator_endpoints": "Staff Session or BasicAuth",
        },
        "endpoints": [
            {"method": "POST", "path": "/api/v1/devices/register/", "auth": "X-Enrollment-Key"},
            {"method": "POST", "path": "/api/v1/devices/sync/", "auth": "Device"},
            {"method": "GET", "path": "/api/v1/devices/status/", "auth": "Device"},
            {"method": "POST", "path": "/api/v1/devices/renew-token/", "auth": "Device"},
            {"method": "GET", "path": "/api/v1/commands/pending/", "auth": "Device"},
            {"method": "POST", "path": "/api/v1/commands/acknowledge/", "auth": "Device"},
            {"method": "GET", "path": "/api/v1/devices/{device_id}/", "auth": "Operator"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/lock/", "auth": "Operator"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/unlock/", "auth": "Operator"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/release/", "auth": "Operator"},
            {"method": "POST", "path": "/api/v1/devices/{device_id}/sync-command/", "auth": "Operator"},
        ],
    })


urlpatterns = [
    path("", RedirectView.as_view(pattern_name="panel", permanent=False)),
    path("admin/", admin.site.urls),
    path("panel/", panel.panel_home, name="panel"),
    path("panel/qr/", panel.panel_qr, name="panel_qr"),
    path("panel/<uuid:device_id>/<str:action>/", panel.panel_action, name="panel_action"),
    path("download/akdevicelock.apk", panel.download_apk, name="download_apk"),
    path("download/testdpc.apk", panel.download_testdpc_apk, name="download_testdpc_apk"),
    path("api/v1/docs/", api_docs, name="api_docs"),
    path("api/v1/devices/", include("devices.urls")),
    path("api/v1/commands/", include("commands.urls")),
]
