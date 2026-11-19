from django.urls import path

from entitlements import views

urlpatterns = [
    path("", views.EntitlementListView.as_view()),
    path("allocate/", views.EntitlementAllocateView.as_view()),
    path("transfer/", views.EntitlementTransferView.as_view()),
    path("balance/", views.EntitlementBalanceView.as_view()),
    path("history/", views.EntitlementHistoryView.as_view()),
    path("consumption/", views.EntitlementConsumptionView.as_view()),
]
