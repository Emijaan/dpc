from django.urls import path

from accounts import auth_views

urlpatterns = [
    path("login/", auth_views.LoginView.as_view()),
    path("refresh/", auth_views.RefreshView.as_view()),
    path("logout/", auth_views.LogoutView.as_view()),
    path("me/", auth_views.MeView.as_view()),
]
