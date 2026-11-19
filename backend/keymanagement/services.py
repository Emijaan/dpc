import base64
import os
import uuid
from datetime import timedelta
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.utils import timezone

from audit.models import log_event
from keymanagement.models import DevicePublicKey, SigningKey


def _export_public(priv_key) -> tuple[str, str]:
    pub = priv_key.public_key()
    pem = pub.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    der = pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return pem, base64.b64encode(der).decode()


def _write_private_key(path: Path, priv_key):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        priv_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def ensure_active_command_key() -> SigningKey:
    active = SigningKey.objects.filter(category=SigningKey.Category.COMMAND, status=SigningKey.Status.ACTIVE).first()
    if active:
        return active
    legacy = Path(settings.SIGNING_KEY_PATH)
    if legacy.exists():
        priv = serialization.load_pem_private_key(legacy.read_bytes(), password=None)
        ref = str(legacy)
    else:
        priv = ec.generate_private_key(ec.SECP256R1())
        _write_private_key(legacy, priv)
        ref = str(legacy)
    pem, b64 = _export_public(priv)
    now = timezone.now()
    return SigningKey.objects.create(
        category=SigningKey.Category.COMMAND,
        version=1,
        public_key_pem=pem,
        public_key_b64=b64,
        private_key_ref=ref,
        status=SigningKey.Status.ACTIVE,
        activated_at=now,
        expires_at=now + timedelta(days=365),
    )


def generate_signing_key(category: str = SigningKey.Category.COMMAND, activate: bool = True,
                         ttl_days: int = 365, request=None) -> SigningKey:
    if activate:
        SigningKey.objects.filter(category=category, status=SigningKey.Status.ACTIVE).update(
            status=SigningKey.Status.ROTATED
        )
    latest = SigningKey.objects.filter(category=category).order_by("-version").first()
    next_ver = (latest.version + 1) if latest else 1
    kid = uuid.uuid4()
    key_path = Path(settings.KEY_STORAGE_DIR) / f"{category.lower()}_v{next_ver}_{kid}.pem"
    priv = ec.generate_private_key(ec.SECP256R1())
    _write_private_key(key_path, priv)
    pem, b64 = _export_public(priv)
    now = timezone.now()
    sk = SigningKey.objects.create(
        id=kid,
        category=category,
        version=next_ver,
        public_key_pem=pem,
        public_key_b64=b64,
        private_key_ref=str(key_path),
        status=SigningKey.Status.ACTIVE if activate else SigningKey.Status.ROTATED,
        activated_at=now if activate else None,
        expires_at=now + timedelta(days=ttl_days),
    )
    log_event(None, "KEY_GENERATED", f"{category} v{next_ver}", key_id=str(sk.id), request=request)
    return sk


def rotate_signing_key(category: str = SigningKey.Category.COMMAND, request=None) -> SigningKey:
    sk = generate_signing_key(category=category, activate=True, request=request)
    log_event(None, "KEY_ROTATED", f"{category} rotated to v{sk.version}", key_id=str(sk.id), request=request)
    return sk


def revoke_signing_key(sk: SigningKey, reason: str = "revoked", request=None):
    from commands.models import DeviceCommand
    now = timezone.now()
    sk.status = SigningKey.Status.REVOKED
    sk.revoked_at = now
    sk.save(update_fields=["status", "revoked_at"])
    # Invalidate any unexecuted commands signed with the revoked key.
    DeviceCommand.objects.filter(
        key_id=str(sk.id),
        command_status__in=[DeviceCommand.Status.PENDING, DeviceCommand.Status.DELIVERED],
    ).update(command_status=DeviceCommand.Status.EXPIRED, execution_result=f"key_revoked:{reason[:100]}")
    log_event(None, "KEY_REVOKED", f"{sk.category} v{sk.version}: {reason}", key_id=str(sk.id), request=request)


def sign_payload(sk: SigningKey, payload: bytes) -> str:
    priv = serialization.load_pem_private_key(Path(sk.private_key_ref).read_bytes(), password=None)
    sig = priv.sign(payload, ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(sig).decode()


def register_device_public_key(device, public_key_b64: str, algorithm: str = "ECDSA_P256",
                               renew: bool = False, request=None) -> DevicePublicKey:
    now = timezone.now()
    if renew:
        DevicePublicKey.objects.filter(device=device, status=DevicePublicKey.Status.ACTIVE).update(
            status=DevicePublicKey.Status.REVOKED, revoked_at=now
        )
    latest = DevicePublicKey.objects.filter(device=device).order_by("-version").first()
    ver = (latest.version + 1) if latest else 1
    kid = f"dev-{str(device.id)[:8]}-v{ver}"
    dpk = DevicePublicKey.objects.create(
        device=device,
        key_id=kid,
        algorithm=algorithm,
        public_key_b64=public_key_b64,
        version=ver,
        status=DevicePublicKey.Status.ACTIVE,
    )
    log_event(
        device,
        "DEVICE_PUBLIC_KEY_RENEWED" if renew else "DEVICE_PUBLIC_KEY_REGISTERED",
        f"v{ver} {algorithm}",
        key_id=kid,
        request=request,
    )
    return dpk

