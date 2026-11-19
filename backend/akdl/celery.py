"""Celery configuration for AK DeviceLock (optional Redis broker; eager fallback in dev/tests)."""
import os

try:
    from celery import Celery

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "akdl.settings")
    app = Celery("akdl")
    app.config_from_object("django.conf:settings", namespace="CELERY")
    app.autodiscover_tasks()
except ImportError:  # Celery is optional in local/minimal test environments
    app = None
