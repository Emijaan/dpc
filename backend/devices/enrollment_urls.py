from django.urls import path

from devices import views

urlpatterns = [
    path("create/", views.EnrollmentListCreateView.as_view()),
    path("<uuid:session_id>/status/", views.EnrollmentStatusView.as_view()),
    path("<uuid:session_id>/complete/", views.EnrollmentCompleteStepView.as_view()),
    path("<uuid:session_id>/cancel/", views.EnrollmentCancelView.as_view()),
    path("<uuid:session_id>/qr/", views.EnrollmentQRView.as_view()),
    path("<uuid:session_id>/bat/", views.EnrollmentBatView.as_view()),
]
