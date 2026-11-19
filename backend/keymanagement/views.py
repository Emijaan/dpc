import base64

from cryptography.hazmat.primitives import serialization
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from devices.auth import DeviceTokenAuthentication, DeviceUser, IsDevice
from devices.models import Device
from devices.ownership import can_access_device, scope_devices_queryset
from keymanagement.models import DevicePublicKey, SigningKey
from keymanagement.services import (
    ensure_active_command_key,
    generate_signing_key,
    register_device_public_key,
    revoke_signing_key,
    rotate_signing_key,
)
from roles.permissions import HasPermissionCode, user_has_perm


def key_dict(sk: SigningKey) -> dict:
    """Public metadata only — never expose private_key_ref or private key material."""
    return {
        "key_id": str(sk.id),
        "category": sk.category,
        "algorithm": sk.algorithm,
        "version": sk.version,
        "status": sk.status,
        "public_key_b64": sk.public_key_b64,
        "activated_at": sk.activated_at.isoformat() if sk.activated_at else None,
        "expires_at": sk.expires_at.isoformat() if sk.expires_at else None,
        "revoked_at": sk.revoked_at.isoformat() if sk.revoked_at else None,
        "created_at": sk.created_at.isoformat(),
    }


class KeyListView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "keys.view"

    def get(self, request):
        ensure_active_command_key()
        keys = [key_dict(k) for k in SigningKey.objects.all()]
        dev_keys = [
            {
                "id": str(dk.id),
                "device_id": str(dk.device_id),
                "key_id": dk.key_id,
                "algorithm": dk.algorithm,
                "version": dk.version,
                "status": dk.status,
                "public_key_b64": dk.public_key_b64,
                "registered_at": dk.registered_at.isoformat(),
            }
            for dk in DevicePublicKey.objects.select_related("device").filter(
                device__in=scope_devices_queryset(request.user)
            )[:100]
        ]
        return Response({"signing_keys": keys, "device_public_keys": dev_keys})


class KeyDetailView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "keys.view"

    def get(self, request, key_id):
        sk = get_object_or_404(SigningKey, pk=key_id)
        return Response(key_dict(sk))


class KeyGenerateView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "keys.manage"

    def post(self, request):
        cat = request.data.get("category", SigningKey.Category.COMMAND)
        if cat not in (SigningKey.Category.ROOT, SigningKey.Category.COMMAND):
            return Response({"error": "invalid_category"}, status=status.HTTP_400_BAD_REQUEST)
        sk = generate_signing_key(category=cat, activate=bool(request.data.get("activate", True)), request=request)
        return Response(key_dict(sk), status=status.HTTP_201_CREATED)


class KeyRotateView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "keys.manage"

    def post(self, request):
        cat = request.data.get("category", SigningKey.Category.COMMAND)
        if cat not in (SigningKey.Category.ROOT, SigningKey.Category.COMMAND):
            return Response({"error": "invalid_category"}, status=status.HTTP_400_BAD_REQUEST)
        sk = rotate_signing_key(category=cat, request=request)
        return Response(key_dict(sk), status=status.HTTP_201_CREATED)


class KeyRevokeView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "keys.manage"

    def post(self, request, key_id):
        sk = get_object_or_404(SigningKey, pk=key_id)
        if sk.status == SigningKey.Status.REVOKED:
            return Response(key_dict(sk))
        revoke_signing_key(sk, reason=request.data.get("reason", "operator_revoked"), request=request)
        return Response(key_dict(sk))


class DevicePublicKeyBundleView(APIView):
    """Device-authenticated endpoint returning active + rotated (transition) public keys and revoked key_ids."""
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [IsDevice]

    def get(self, request):
        ensure_active_command_key()
        valid = [
            {"key_id": str(k.id), "version": k.version, "status": k.status, "public_key_b64": k.public_key_b64}
            for k in SigningKey.objects.filter(
                category=SigningKey.Category.COMMAND,
                status__in=[SigningKey.Status.ACTIVE, SigningKey.Status.ROTATED],
            )
        ]
        revoked = [
            str(k.id)
            for k in SigningKey.objects.filter(category=SigningKey.Category.COMMAND, status=SigningKey.Status.REVOKED)
        ]
        return Response({"valid_keys": valid, "revoked_key_ids": revoked})


class DeviceKeySerializer(serializers.Serializer):
    public_key_b64 = serializers.CharField(max_length=2048)
    algorithm = serializers.CharField(max_length=32, required=False, default="ECDSA_P256")

    def validate_public_key_b64(self, value):
        try:
            der = base64.b64decode(value, validate=True)
            serialization.load_der_public_key(der)
        except Exception:
            raise serializers.ValidationError("Invalid X.509 DER base64 public key")
        return value


class CanRegisterDeviceKey(BasePermission):
    def has_permission(self, request, view):
        if isinstance(request.user, DeviceUser):
            return str(request.user.device.id) == str(view.kwargs.get("device_id"))
        return user_has_perm(request.user, "keys.manage")


class DeviceKeyRegisterView(APIView):
    """Allows an authenticated device (for itself) or an authorized operator to register/renew a device public key."""
    authentication_classes = [DeviceTokenAuthentication] + list(APIView.authentication_classes)
    permission_classes = [CanRegisterDeviceKey]
    renew = False

    def post(self, request, device_id):
        device = get_object_or_404(Device, pk=device_id)
        if not isinstance(request.user, DeviceUser) and not can_access_device(request.user, device):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        s = DeviceKeySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        dpk = register_device_public_key(
            device, d["public_key_b64"], algorithm=d["algorithm"], renew=self.renew, request=request
        )
        return Response(
            {"key_id": dpk.key_id, "version": dpk.version, "status": dpk.status},
            status=status.HTTP_201_CREATED,
        )


class DeviceKeyRenewView(DeviceKeyRegisterView):
    renew = True
