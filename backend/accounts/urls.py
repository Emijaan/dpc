from django.urls import path

from accounts import views
from roles.views import AccountRolesView

urlpatterns = [
    path("", views.AccountListCreateView.as_view()),
    path("<int:account_id>/status/", views.AccountStatusView.as_view()),
    path("<int:account_id>/roles/", AccountRolesView.as_view()),
]

