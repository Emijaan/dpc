import base64
import hashlib
import hmac
import os

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    raw = os.environ.get("AKDL_DATA_ENCRYPTION_KEY", "") or settings.SECRET_KEY
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_value(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_value(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def hash_identifier(value: str) -> str:
    if not value:
        return ""
    key = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(key, value.strip().encode("utf-8"), hashlib.sha256).hexdigest()


def mask_imei(imei: str) -> str:
    s = (imei or "").strip()
    if not s:
        return ""
    if len(s) <= 4:
        return "*" * len(s)
    return "*" * (len(s) - 4) + s[-4:]


def mask_mobile(mobile: str) -> str:
    s = (mobile or "").strip()
    if not s:
        return ""
    if len(s) <= 4:
        return "*" * len(s)
    return "*" * (len(s) - 4) + s[-4:]


def mask_email(email: str) -> str:
    s = (email or "").strip()
    if not s or "@" not in s:
        return "" if not s else "***"
    local, domain = s.split("@", 1)
    prefix = local[0] if local else "*"
    return f"{prefix}***@{domain}"
