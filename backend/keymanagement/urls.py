from django.urls import path

from keymanagement import views

urlpatterns = [
    path("", views.KeyListView.as_view()),
    path("public/", views.DevicePublicKeyBundleView.as_view()),
    path("generate/", views.KeyGenerateView.as_view()),
    path("rotate/", views.KeyRotateView.as_view()),
    path("<uuid:key_id>/", views.KeyDetailView.as_view()),
    path("<uuid:key_id>/revoke/", views.KeyRevokeView.as_view()),
]

