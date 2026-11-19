from django.urls import path

from devices import views

urlpatterns = [
    path("register/", views.RegisterView.as_view()),
    path("sync/", views.SyncView.as_view()),
    path("status/", views.StatusView.as_view()),
    path("renew-token/", views.RenewTokenView.as_view()),
    path("<uuid:device_id>/", views.DeviceInfoView.as_view()),
    path("<uuid:device_id>/lock/", views.LockView.as_view()),
    path("<uuid:device_id>/unlock/", views.UnlockView.as_view()),
    path("<uuid:device_id>/release/", views.ReleaseView.as_view()),
    path("<uuid:device_id>/sync-command/", views.SyncCommandView.as_view()),
]

