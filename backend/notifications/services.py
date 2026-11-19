"""Firebase Cloud Messaging (FCM HTTP v1) notification channel.

FCM only sends a data-only wakeup ('commands_available'). The device must still
authenticate to the backend and verify the ECDSA P-256 signature on every command.
If AKDL_FCM_SERVICE_ACCOUNT is not configured or the device has no fcm_token,
notify_commands_available() is a safe no-op returning False.
"""
import base64
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from audit.models import log_event


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _oauth_access_token(sa: dict) -> str:
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = _b64url(json.dumps({
        "iss": sa["client_email"],
        "scope": "https://www.googleapis.com/auth/firebase.messaging",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }).encode())
    signing_input = f"{header}.{claims}".encode("ascii")
    key = serialization.load_pem_private_key(sa["private_key"].encode("utf-8"), password=None)
    sig = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    assertion = f"{header}.{claims}.{_b64url(sig)}"

    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))["access_token"]


def notify_commands_available(device) -> bool:
    sa_path = os.environ.get("AKDL_FCM_SERVICE_ACCOUNT", "")
    if not sa_path or not device.fcm_token or not Path(sa_path).exists():
        return False
    try:
        sa = json.loads(Path(sa_path).read_text(encoding="utf-8"))
        project_id = os.environ.get("AKDL_FCM_PROJECT_ID") or sa["project_id"]
        token = _oauth_access_token(sa)
        payload = json.dumps({
            "message": {
                "token": device.fcm_token,
                "data": {"event": "commands_available", "device_id": str(device.id)},
                "android": {"priority": "high"},
            }
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            ok = 200 <= resp.status < 300
        log_event(device, "FCM_NOTIFY", "sent" if ok else "failed")
        return ok
    except Exception as exc:
        log_event(device, "FCM_NOTIFY_ERROR", str(exc)[:200])
        return False
