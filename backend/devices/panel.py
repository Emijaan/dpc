import json

import segno
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_safe

from audit.models import DeviceAuditLog, log_event
from commands.models import DeviceCommand
from commands.services import create_command, expire_stale
from devices.models import Device
from keymanagement.models import DevicePublicKey, SigningKey
from keymanagement.services import (
    ensure_active_command_key,
    generate_signing_key,
    revoke_signing_key,
    rotate_signing_key,
)
from notifications.services import notify_commands_available
from roles.models import AccountRole, Permission, Role
from roles.permissions import ensure_default_rbac, get_user_permissions, user_has_perm

ACTIONS = {
    "lock": (DeviceCommand.Type.LOCK, "devices.lock"),
    "unlock": (DeviceCommand.Type.UNLOCK, "devices.unlock"),
    "sync": (DeviceCommand.Type.SYNC, "devices.sync"),
    "release": (DeviceCommand.Type.RELEASE, "devices.release"),
}

ADMIN_COMPONENT = "com.akdevicelock.dpc/com.akdevicelock.dpc.deviceadmin.AkDeviceAdminReceiver"
TESTDPC_COMPONENT = "com.afwsamples.testdpc/com.afwsamples.testdpc.DeviceAdminReceiver"
TESTDPC_URL = "https://dpc.apinfotechandcybersolution.com/download/testdpc.apk"
TESTDPC_CHECKSUM = "gJD2YwtOiWJHkSMkkIfLRlj-quNqG1fb6v100QmzM9w"


@staff_member_required
def panel_home(request):
    ensure_default_rbac()
    ensure_active_command_key()
    perms = get_user_permissions(request.user)
    if not perms:
        return HttpResponseForbidden("No role/permissions assigned to your account.")

    rows = []
    online_count = 0
    locked_count = 0
    if "devices.view" in perms:
        for d in Device.objects.all().order_by("-last_seen"):
            expire_stale(d)
            last = d.commands.first()
            is_on = d.is_online
            if is_on:
                online_count += 1
            if d.restriction_status == Device.Restriction.LOCKED:
                locked_count += 1
            rows.append({"device": d, "online": is_on, "last": last})

    recent_commands = DeviceCommand.objects.select_related("device").all()[:25] if "commands.view" in perms else []
    roles_list = Role.objects.prefetch_related("permissions").all() if "roles.manage" in perms else []
    all_perms = Permission.objects.all() if "roles.manage" in perms else []
    accounts = get_user_model().objects.prefetch_related("account_roles__role").all().order_by("id") if (
        "roles.manage" in perms or "accounts.manage" in perms
    ) else []
    signing_keys = SigningKey.objects.all() if "keys.view" in perms else []
    device_keys = DevicePublicKey.objects.select_related("device").all()[:50] if "keys.view" in perms else []
    audit_logs = DeviceAuditLog.objects.select_related("actor", "device", "command").all()[:50] if "audit.view" in perms else []

    ctx = {
        "perms": perms,
        "rows": rows,
        "total_count": len(rows),
        "online_count": online_count,
        "locked_count": locked_count,
        "unlocked_count": len(rows) - locked_count,
        "recent_commands": recent_commands,
        "roles_list": roles_list,
        "all_perms": all_perms,
        "accounts": accounts,
        "signing_keys": signing_keys,
        "device_keys": device_keys,
        "audit_logs": audit_logs,
    }
    return render(request, "panel.html", ctx)


@staff_member_required
@require_POST
def panel_action(request, device_id, action):
    entry = ACTIONS.get(action)
    if not entry:
        return redirect("panel")
    ctype, req_perm = entry
    if not user_has_perm(request.user, req_perm):
        return HttpResponseForbidden(f"Missing permission: {req_perm}")
    device = get_object_or_404(Device, pk=device_id)
    if device.enrollment_status == Device.Enrollment.ENROLLED:
        busy = device.commands.filter(
            command_type=ctype,
            command_status__in=[DeviceCommand.Status.PENDING, DeviceCommand.Status.DELIVERED],
        ).exists()
        if not busy:
            create_command(device, ctype, "operator panel", request=request)
            notify_commands_available(device)
    return redirect("panel")


@staff_member_required
@require_POST
def panel_create_role(request):
    if not user_has_perm(request.user, "roles.manage"):
        return HttpResponseForbidden("Missing permission: roles.manage")
    name = request.POST.get("name", "").strip()
    desc = request.POST.get("description", "").strip()
    perm_codes = request.POST.getlist("permissions")
    if name and not Role.objects.filter(name=name).exists():
        role = Role.objects.create(name=name, description=desc, is_system=False)
        if perm_codes:
            role.permissions.set(Permission.objects.filter(code__in=perm_codes))
        log_event(None, "ROLE_CREATED", f"role={name} perms={perm_codes}", request=request)
    return redirect("/panel/#roles")


@staff_member_required
@require_POST
def panel_assign_role(request):
    if not user_has_perm(request.user, "roles.manage"):
        return HttpResponseForbidden("Missing permission: roles.manage")
    user = get_object_or_404(get_user_model(), pk=request.POST.get("account_id"))
    role = get_object_or_404(Role, pk=request.POST.get("role_id"))
    if role.name == "SUPER_ADMIN" and not request.user.is_superuser:
        return HttpResponseForbidden("Only Super Admin can assign SUPER_ADMIN")
    AccountRole.objects.filter(user=user).delete()
    AccountRole.objects.create(user=user, role=role, assigned_by=request.user)
    log_event(None, "ACCOUNT_ROLES_ASSIGNED", f"user={user.username} role={role.name}", request=request)
    return redirect("/panel/#roles")


@staff_member_required
@require_POST
def panel_create_account(request):
    if not user_has_perm(request.user, "accounts.manage"):
        return HttpResponseForbidden("Missing permission: accounts.manage")
    U = get_user_model()
    uname = request.POST.get("username", "").strip()
    pw = request.POST.get("password", "")
    role_id = request.POST.get("role_id")
    if uname and len(pw) >= 8 and not U.objects.filter(username=uname).exists():
        role = Role.objects.filter(pk=role_id).first() if role_id else None
        if role and role.name == "SUPER_ADMIN" and not request.user.is_superuser:
            return HttpResponseForbidden("Cannot create SUPER_ADMIN")
        u = U.objects.create_user(username=uname, password=pw, is_staff=True)
        if role:
            AccountRole.objects.create(user=u, role=role, assigned_by=request.user)
        log_event(None, "ACCOUNT_CREATED", f"user={uname}", request=request)
    return redirect("/panel/#roles")


@staff_member_required
@require_POST
def panel_key_action(request, action):
    if not user_has_perm(request.user, "keys.manage"):
        return HttpResponseForbidden("Missing permission: keys.manage")
    if action == "generate":
        cat = request.POST.get("category", SigningKey.Category.COMMAND)
        if cat in (SigningKey.Category.ROOT, SigningKey.Category.COMMAND):
            generate_signing_key(category=cat, activate=True, request=request)
    elif action == "rotate":
        rotate_signing_key(category=SigningKey.Category.COMMAND, request=request)
    elif action == "revoke":
        sk = get_object_or_404(SigningKey, pk=request.POST.get("key_id"))
        if sk.status != SigningKey.Status.REVOKED:
            revoke_signing_key(sk, reason="panel_revoked", request=request)
    return redirect("/panel/#keys")


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
    """Step-1 QR payload for Android 12–15 devices: installs Google Test DPC first, then transfers ownership."""
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
