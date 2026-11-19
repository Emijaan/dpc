from rest_framework import authentication, exceptions, permissions

from devices.models import Device


class DeviceUser:
    """Minimal principal so DRF throttling/permissions work for device callers."""
    is_authenticated = True
    is_staff = False

    def __init__(self, device):
        self.device = device
        self.pk = str(device.id)


class DeviceTokenAuthentication(authentication.BaseAuthentication):
    keyword = "Device"

    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            return None
        device = Device.objects.filter(auth_token_hash=Device.hash_token(parts[1])).first()
        if device is None:
            raise exceptions.AuthenticationFailed("Invalid device credential")
        if device.enrollment_status == Device.Enrollment.RELEASED:
            raise exceptions.AuthenticationFailed("Device released")
        return DeviceUser(device), None

    def authenticate_header(self, request):
        return self.keyword


class IsDevice(permissions.BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, DeviceUser)

