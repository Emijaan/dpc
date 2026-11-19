import json

import segno
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_safe

from commands.models import DeviceCommand
from commands.services import create_command, expire_stale
from devices.models import Device

ACTIONS = {
    "lock": DeviceCommand.Type.LOCK,
    "unlock": DeviceCommand.Type.UNLOCK,
    "sync": DeviceCommand.Type.SYNC,
    "release": DeviceCommand.Type.RELEASE,
}

ADMIN_COMPONENT = "com.akdevicelock.dpc/com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver"
TESTDPC_COMPONENT = "com.afwsamples.testdpc/com.afwsamples.testdpc.DeviceAdminReceiver"
# Official Google-signed Test DPC v9.0.12 (before Google disabled transferOwnership in v9.0.16)
TESTDPC_URL = "https://dpc.apinfotechandcybersolution.com/download/testdpc.apk"
TESTDPC_CHECKSUM = "gJD2YwtOiWJHkSMkkIfLRlj-quNqG1fb6v100QmzM9w"


@staff_member_required
def panel_home(request):
    rows = []
    online_count = 0
    locked_count = 0
    for d in Device.objects.all().order_by("-last_seen"):
        expire_stale(d)
        last = d.commands.first()
        is_on = d.is_online
        if is_on:
            online_count += 1
        if d.restriction_status == Device.Restriction.LOCKED:
            locked_count += 1
        rows.append({"device": d, "online": is_on, "last": last})
    ctx = {
        "rows": rows,
        "total_count": len(rows),
        "online_count": online_count,
        "locked_count": locked_count,
        "unlocked_count": len(rows) - locked_count,
    }
    return render(request, "panel.html", ctx)


@staff_member_required
@require_POST
def panel_action(request, device_id, action):
    device = get_object_or_404(Device, pk=device_id)
    ctype = ACTIONS.get(action)
    if ctype and device.enrollment_status == Device.Enrollment.ENROLLED:
        busy = device.commands.filter(
            command_type=ctype,
            command_status__in=[DeviceCommand.Status.PENDING, DeviceCommand.Status.DELIVERED],
        ).exists()
        if not busy:
            create_command(device, ctype, "operator panel")
    return redirect("panel")


def provisioning_payload(base_url: str | None = None) -> dict:
    """Direct 1-step Android QR provisioning payload (Device Owner)."""
    base = (base_url or settings.PUBLIC_BASE_URL).rstrip("/")
    return {
        "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME": ADMIN_COMPONENT,
        "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION": f"{base}/download/akdevicelock.apk",
        "android.app.extra.PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM": settings.APK_CERT_SHA256,
        "android.app.extra.PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED": True,
        "android.app.extra.PROVISIONING_SKIP_ENCRYPTION": True,
        "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE": {
            "server_url": base,
            "enrollment_key": settings.ENROLLMENT_KEY,
        },
    }


def testdpc_provisioning_payload() -> dict:
    """Step-1 QR payload for Android 13/14/15+ devices: installs Google Test DPC first, then transfers ownership."""
    return {
        "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME": TESTDPC_COMPONENT,
        "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION": TESTDPC_URL,
        "android.app.extra.PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM": TESTDPC_CHECKSUM,
        "android.app.extra.PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED": True,
        "android.app.extra.PROVISIONING_SKIP_ENCRYPTION": True,
    }


@staff_member_required
@require_safe
def panel_qr(request):
    if not settings.APK_CERT_SHA256:
        return HttpResponse("APK certificate checksum not configured (AKDL_APK_CERT_SHA256).", status=503)
    req_base = request.GET.get("base_url") or (
        f"{request.scheme}://{request.get_host()}" if settings.PUBLIC_BASE_URL == "auto" else settings.PUBLIC_BASE_URL
    )
    payload_dict = provisioning_payload(req_base)
    apk_url = payload_dict["android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION"]
    direct_svg = segno.make(json.dumps(payload_dict, separators=(",", ":")), error="m").svg_inline(scale=4, border=3)
    testdpc_svg = segno.make(json.dumps(testdpc_provisioning_payload(), separators=(",", ":")), error="m").svg_inline(scale=4, border=3)
    apk_url_svg = segno.make(apk_url, error="m").svg_inline(scale=5, border=3)
    return render(
        request,
        "qr.html",
        {
            "svg": direct_svg,
            "testdpc_svg": testdpc_svg,
            "apk_url_svg": apk_url_svg,
            "base_url": req_base,
            "apk_url": apk_url,
            "admin_component": ADMIN_COMPONENT,
        },
    )


@require_safe
def download_apk(request):
    """Public: the provisioning flow downloads this before the device has any credential."""
    try:
        return FileResponse(
            open(settings.APK_PATH, "rb"),
            as_attachment=True,
            filename="akdevicelock.apk",
            content_type="application/vnd.android.package-archive",
        )
    except FileNotFoundError:
        raise Http404


@require_safe
def download_testdpc_apk(request):
    """Serves Google-signed TestDPC v9.0.12 (which supports transferOwnership)."""
    import os
    path = os.environ.get("AKDL_TESTDPC_PATH", "/etc/akdl/testdpc.apk")
    try:
        return FileResponse(
            open(path, "rb"),
            as_attachment=True,
            filename="TestDPC_9.0.12.apk",
            content_type="application/vnd.android.package-archive",
        )
    except FileNotFoundError:
        raise Http404
