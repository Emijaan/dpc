"""Command signing. ECDSA P-256 / SHA-256; Android verifies with java.security (SHA256withECDSA)."""
import base64
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings


def canonical_payload(command) -> bytes:
    """Exact byte string that is signed. The Android app must rebuild it identically."""
    fields = [
        str(command.id), str(command.device_id), command.command_type,
        str(int(command.issued_at.timestamp())), str(int(command.expires_at.timestamp())),
        command.nonce, command.reason,
    ]
    return "|".join(fields).encode("utf-8")


def _private_key():
    return serialization.load_pem_private_key(Path(settings.SIGNING_KEY_PATH).read_bytes(), password=None)


def sign(command) -> str:
    sig = _private_key().sign(canonical_payload(command), ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(sig).decode()


def public_key_b64() -> str:
    """X.509 SubjectPublicKeyInfo DER, base64: embed this in the Android app (public data)."""
    pub = _private_key().public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(pub).decode()


def generate_key(path: str):
    key = ec.generate_private_key(ec.SECP256R1())
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))

