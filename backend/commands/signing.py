"""Command signing. ECDSA P-256 / SHA-256; delegates key lifecycle to keymanagement."""
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from keymanagement.services import ensure_active_command_key, sign_payload


def canonical_payload(command) -> bytes:
    """Exact byte string that is signed. The Android app must rebuild it identically."""
    fields = [
        str(command.id), str(command.device_id), command.command_type,
        str(int(command.issued_at.timestamp())), str(int(command.expires_at.timestamp())),
        command.nonce, command.reason,
    ]
    if getattr(command, "key_id", ""):
        fields.append(str(command.key_id))
    return "|".join(fields).encode("utf-8")


def sign_command(command) -> str:
    sk = ensure_active_command_key()
    command.key_id = str(sk.id)
    return sign_payload(sk, canonical_payload(command))


def sign(command) -> str:
    return sign_command(command)


def public_key_b64() -> str:
    return ensure_active_command_key().public_key_b64


def generate_key(path: str):
    key = ec.generate_private_key(ec.SECP256R1())
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
