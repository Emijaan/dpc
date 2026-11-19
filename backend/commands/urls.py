from django.urls import path

from commands import views

urlpatterns = [
    path("pending/", views.PendingView.as_view()),
    path("acknowledge/", views.AcknowledgeView.as_view()),
]

