from django.urls import path

from devices import views
from keymanagement.views import DeviceKeyRegisterView, DeviceKeyRenewView

urlpatterns = [
    path("", views.DeviceListView.as_view()),
    path("export/", views.DeviceExportView.as_view()),
    path("register/", views.RegisterView.as_view()),
    path("sync/", views.SyncView.as_view()),
    path("status/", views.StatusView.as_view()),
    path("photo/", views.DevicePhotoUploadView.as_view()),
    path("renew-token/", views.RenewTokenView.as_view()),
    path("frp-policy/", views.GlobalFrpPolicyView.as_view()),
    path("<uuid:device_id>/", views.DeviceInfoView.as_view()),
    path("<uuid:device_id>/reveal-imei/", views.DeviceRevealImeiView.as_view()),
    path("<uuid:device_id>/photo/", views.DevicePhotoView.as_view()),
    path("<uuid:device_id>/lock/", views.LockView.as_view()),
    path("<uuid:device_id>/unlock/", views.UnlockView.as_view()),
    path("<uuid:device_id>/release/", views.ReleaseView.as_view()),
    path("<uuid:device_id>/sync/", views.SyncCommandView.as_view()),
    path("<uuid:device_id>/sync-command/", views.SyncCommandView.as_view()),
    path("<uuid:device_id>/status-command/", views.StatusCommandView.as_view()),
    path("<uuid:device_id>/locate/", views.LocateView.as_view()),
    path("<uuid:device_id>/capture-photo/", views.CapturePhotoView.as_view()),
    path("<uuid:device_id>/camera/", views.CameraPolicyView.as_view()),
    path("<uuid:device_id>/gps-policy/", views.GpsPolicyView.as_view()),
    path("<uuid:device_id>/network-policy/", views.NetworkPolicyView.as_view()),
    path("<uuid:device_id>/update-agent/", views.AgentUpdateView.as_view()),
    path("<uuid:device_id>/transfer/", views.DeviceTransferView.as_view()),
    path("<uuid:device_id>/keys/register/", DeviceKeyRegisterView.as_view()),
    path("<uuid:device_id>/keys/renew/", DeviceKeyRenewView.as_view()),
]
