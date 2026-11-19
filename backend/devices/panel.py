import json

import segno
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from commands.models import DeviceCommand
from commands.services import create_command, expire_stale
from devices.models import Device

ACTIONS = {
    "lock": DeviceCommand.Type.LOCK,
    "unlock": DeviceCommand.Type.UNLOCK,
    "sync": DeviceCommand.Type.SYNC,
}

ADMIN_COMPONENT = "com.akdevicelock.dpc/com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver"


@staff_member_required
def panel_home(request):
    rows = []
    for d in Device.objects.all().order_by("-last_seen"):
        expire_stale(d)
        last = d.commands.first()
        rows.append({"device": d, "online": d.is_online, "last": last})
    return render(request, "panel.html", {"rows": rows})


@staff_member_required
@require_POST
def panel_action(request, device_id, action):
    device = get_object_or_404(Device, pk=device_id)
    ctype = ACTIONS.get(action)
    if ctype and device.enrollment_status == Device.Enrollment.ENROLLED:
        busy = device.commands.filter(
            command_type=ctype,
            command_status__in=[DeviceCommand.Status.PENDING, DeviceCommand.Status.DELIVERED]).exists()
        if not busy:
            create_command(device, ctype, "operator panel")
    return redirect("panel")


def provisioning_payload(base_url: str | None = None) -> dict:
    """Android QR provisioning payload (Device Owner). Contains the enrollment key: keep the QR private."""
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


@staff_member_required
@require_GET
def panel_qr(request):
    if not settings.APK_CERT_SHA256:
        return HttpResponse("APK certificate checksum not configured (AKDL_APK_CERT_SHA256).", status=503)
    req_base = request.GET.get("base_url") or (
        f"{request.scheme}://{request.get_host()}" if settings.PUBLIC_BASE_URL == "auto" else settings.PUBLIC_BASE_URL
    )
    payload_dict = provisioning_payload(req_base)
    payload = json.dumps(payload_dict, separators=(",", ":"))
    svg = segno.make(payload, error="m").svg_inline(scale=5, border=4)
    return render(request, "qr.html", {"svg": svg, "base_url": req_base, "apk_url": payload_dict["android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION"]})


@require_GET
def download_apk(request):
    """Public: the provisioning flow downloads this before the device has any credential."""
    try:
        return FileResponse(open(settings.APK_PATH, "rb"), as_attachment=True,
                            filename="akdevicelock.apk",
                            content_type="application/vnd.android.package-archive")
    except FileNotFoundError:
        raise Http404
