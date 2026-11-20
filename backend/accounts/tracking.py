"""Tracks every authenticated user's IP address and client device/browser."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.models import AccountProfile
from audit.models import client_device_info, client_ip, log_event


def record_user_access(user, request, force: bool = False):
    if not user or not getattr(user, "is_authenticated", False):
        return
    if not isinstance(user, get_user_model()):
        return
    ip = client_ip(request)
    cdev, ua = client_device_info(request)
    now = timezone.now()

    prof = AccountProfile.objects.filter(user=user).first()
    if prof is None:
        acct_type = (
            AccountProfile.AccountType.SUPERUSER
            if getattr(user, "is_superuser", False)
            else AccountProfile.AccountType.RETAILER
        )
        prof, _ = AccountProfile.objects.get_or_create(
            user=user,
            defaults={
                "account_type": acct_type,
                "last_ip": ip,
                "last_device": cdev,
                "last_user_agent": ua,
                "last_active_at": now,
            },
        )
        return

    changed = (prof.last_ip != ip) or (prof.last_device != cdev) or (prof.last_user_agent != ua)
    stale = prof.last_active_at is None or (now - prof.last_active_at) > timedelta(seconds=60)
    if force or changed or stale:
        AccountProfile.objects.filter(pk=prof.pk).update(
            last_ip=ip,
            last_device=cdev,
            last_user_agent=ua,
            last_active_at=now,
        )


class TrackedJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        res = super().authenticate(request)
        if res is not None:
            user, _token = res
            record_user_access(user, request)
        return res


class UserAccessTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(request, "user", None) and getattr(request.user, "is_authenticated", False):
            record_user_access(request.user, request)
        return self.get_response(request)


def on_session_login(sender, request, user, **kwargs):
    record_user_access(user, request, force=True)
    log_event(None, "LOGIN_SUCCESS", f"user={user.username} method=session", actor=user, request=request)
