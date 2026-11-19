from django.urls import path

from accounts import views

urlpatterns = [
    path("", views.VendorListCreateView.as_view()),
    path("<uuid:vendor_id>/", views.VendorDetailView.as_view()),
]
