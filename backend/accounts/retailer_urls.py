from django.urls import path

from accounts import views

urlpatterns = [
    path("", views.RetailerListCreateView.as_view()),
    path("<uuid:retailer_id>/", views.RetailerDetailView.as_view()),
]
