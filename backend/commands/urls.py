from django.urls import path

from commands import views
from devices.views import CommandHistoryView

urlpatterns = [
    path("", CommandHistoryView.as_view()),
    path("pending/", views.PendingView.as_view()),
    path("acknowledge/", views.AcknowledgeView.as_view()),
]

