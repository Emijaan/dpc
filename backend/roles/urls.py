from django.urls import path

from roles import views

urlpatterns = [
    path("", views.RoleListCreateView.as_view()),
    path("<int:role_id>/", views.RoleDetailView.as_view()),
    path("<int:role_id>/permissions/", views.RolePermissionsView.as_view()),
]

