from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from devices import panel

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="panel", permanent=False)),
    path("admin/", admin.site.urls),
    path("panel/", panel.panel_home, name="panel"),
    path("panel/qr/", panel.panel_qr, name="panel_qr"),
    path("panel/<uuid:device_id>/<str:action>/", panel.panel_action, name="panel_action"),
    path("download/akdevicelock.apk", panel.download_apk, name="download_apk"),
    path("download/testdpc.apk", panel.download_testdpc_apk, name="download_testdpc_apk"),
    path("api/v1/devices/", include("devices.urls")),
    path("api/v1/commands/", include("commands.urls")),
]
