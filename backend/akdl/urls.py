from django.contrib import admin
from django.urls import include, path

from devices import panel

urlpatterns = [
    path("admin/", admin.site.urls),
    path("panel/", panel.panel_home, name="panel"),
    path("panel/<uuid:device_id>/<str:action>/", panel.panel_action, name="panel_action"),
    path("api/v1/devices/", include("devices.urls")),
    path("api/v1/commands/", include("commands.urls")),
]
