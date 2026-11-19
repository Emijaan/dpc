from django.urls import path

from accounts import views
from roles.views import AccountRolesView

urlpatterns = [
    path("", views.AccountListCreateView.as_view()),
    path("<int:account_id>/", views.AccountDetailView.as_view()),
    path("<int:account_id>/activate/", views.AccountActivateView.as_view()),
    path("<int:account_id>/deactivate/", views.AccountDeactivateView.as_view()),
    path("<int:account_id>/status/", views.AccountStatusView.as_view()),
    path("<int:account_id>/quota/", views.AccountQuotaView.as_view()),
    path("<int:account_id>/roles/", AccountRolesView.as_view()),
]
