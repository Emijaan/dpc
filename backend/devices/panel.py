import json
import secrets
import uuid

import segno
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_safe

from accounts.models import AccountProfile
from accounts.services import create_account_with_profile, delete_or_disable_account, set_account_active
from audit.models import log_event
from commands.models import DeviceCommand
from commands.services import create_command, expire_stale
from devices.models import Customer, Device, EnrollmentSession
from devices.ownership import (
    can_access_device,
    can_access_enrollment,
    can_manage_account,
    get_account_type,
    get_ownership_context_for_creator,
    is_superuser_account,
    scope_accounts_queryset,
    scope_audit_logs_queryset,
    scope_commands_queryset,
    scope_devices_queryset,
    scope_enrollments_queryset,
)
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
    "locate": (DeviceCommand.Type.LOCATE, "devices.sync"),
    "photo": (DeviceCommand.Type.CAPTURE_PHOTO, "devices.lock"),
    "camera_off": (DeviceCommand.Type.CAMERA_DISABLE, "devices.lock"),
    "camera_on": (DeviceCommand.Type.CAMERA_ENABLE, "devices.lock"),
    "gps_on": (DeviceCommand.Type.GPS_FORCE_ON, "devices.lock"),
    "gps_unlock": (DeviceCommand.Type.GPS_UNLOCK, "devices.lock"),
    "net_lock": (DeviceCommand.Type.NETWORK_RESTRICT, "devices.lock"),
    "net_unlock": (DeviceCommand.Type.NETWORK_ALLOW, "devices.lock"),
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
        for d in scope_devices_queryset(request.user).select_related("customer", "retailer", "vendor").order_by("-last_seen"):
            expire_stale(d)
            last = d.commands.first()
            is_on = d.is_online
            if is_on:
                online_count += 1
            if d.restriction_status == Device.Restriction.LOCKED:
                locked_count += 1
            rows.append({"device": d, "online": is_on, "last": last})

    recent_commands = scope_commands_queryset(request.user).select_related("device")[:25] if "commands.view" in perms else []
    roles_list = Role.objects.prefetch_related("permissions").all() if ("roles.manage" in perms or "accounts.manage" in perms) else []
    all_perms = Permission.objects.all() if "roles.manage" in perms else []
    accounts = scope_accounts_queryset(request.user).select_related("profile", "profile__retailer").prefetch_related("account_roles__role").order_by("id") if (
        "roles.manage" in perms or "accounts.manage" in perms
    ) else []
    retailers = [
        a for a in accounts
        if getattr(getattr(a, "profile", None), "account_type", None) == AccountProfile.AccountType.RETAILER
    ]
    enrollments = (
        scope_enrollments_queryset(request.user).select_related("customer", "retailer", "vendor")[:30]
        if ("enrollments.manage" in perms or "devices.view" in perms)
        else []
    )
    signing_keys = SigningKey.objects.all() if "keys.view" in perms else []
    device_keys = DevicePublicKey.objects.select_related("device").filter(
        device__in=scope_devices_queryset(request.user)
    )[:50] if "keys.view" in perms else []
    audit_logs = scope_audit_logs_queryset(request.user).select_related("actor", "device", "command")[:50] if "audit.view" in perms else []

    ctx = {
        "perms": perms,
        "account_type": get_account_type(request.user),
        "my_profile": AccountProfile.objects.filter(user=request.user).first(),
        "panel_msg": request.session.pop("panel_msg", None),
        "rows": rows,
        "total_count": len(rows),
        "online_count": online_count,
        "locked_count": locked_count,
        "unlocked_count": len(rows) - locked_count,
        "recent_commands": recent_commands,
        "roles_list": roles_list,
        "all_perms": all_perms,
        "accounts": accounts,
        "retailers": retailers,
        "enrollments": enrollments,
        "new_enrollment_token": request.session.pop("new_enrollment_token", None),
        "new_enrollment_id": request.session.pop("new_enrollment_id", None),
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
    if not can_access_device(request.user, device):
        return HttpResponseForbidden("Device is outside your ownership boundary.")
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
    if not can_manage_account(request.user, user):
        return HttpResponseForbidden("Account is outside your ownership boundary.")
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
        actor_type = get_account_type(request.user)
        target_type = request.POST.get("account_type", AccountProfile.AccountType.VENDOR)
        if actor_type == AccountProfile.AccountType.RETAILER:
            if target_type != AccountProfile.AccountType.VENDOR:
                return HttpResponseForbidden("Retailer can only create Vendor accounts.")
            retailer_obj = request.user
        elif actor_type != AccountProfile.AccountType.SUPERUSER:
            return HttpResponseForbidden("Forbidden")
        else:
            ret_id = request.POST.get("retailer_id")
            retailer_obj = U.objects.filter(pk=ret_id).first() if ret_id else None
        raw_quota = request.POST.get("entitlement_quota", "").strip()
        quota = int(raw_quota) if raw_quota.isdigit() else None
        role = Role.objects.filter(pk=role_id).first() if role_id else Role.objects.filter(name=target_type).first()
        if role and role.name == "SUPER_ADMIN" and not request.user.is_superuser:
            return HttpResponseForbidden("Cannot create SUPER_ADMIN")
        if target_type == AccountProfile.AccountType.VENDOR and not retailer_obj:
            target_type = AccountProfile.AccountType.RETAILER
        create_account_with_profile(
            created_by=request.user,
            username=uname,
            password=pw,
            account_type=target_type,
            retailer_user=retailer_obj,
            entitlement_quota=quota,
            role_ids=[role.id] if role else [],
            request=request,
        )
    return redirect("/panel/#users")


@staff_member_required
@require_POST
def panel_set_quota(request, account_id):
    if not user_has_perm(request.user, "accounts.manage"):
        return HttpResponseForbidden("Missing permission: accounts.manage")
    target = get_object_or_404(get_user_model(), pk=account_id)
    if not can_manage_account(request.user, target):
        return HttpResponseForbidden("Account is outside your ownership boundary.")
    profile, _ = AccountProfile.objects.get_or_create(
        user=target,
        defaults={
            "account_type": AccountProfile.AccountType.SUPERUSER
            if target.is_superuser
            else AccountProfile.AccountType.RETAILER
        },
    )
    action = request.POST.get("action", "").strip()
    delta_raw = request.POST.get("delta", "").strip()
    if action == "remove":
        quota = None
    elif delta_raw:
        try:
            delta = int(delta_raw)
        except ValueError:
            return redirect("/panel/#users")
        base = profile.entitlement_quota if profile.entitlement_quota is not None else 0
        quota = max(0, base + delta)
    else:
        raw_quota = request.POST.get("entitlement_quota", "").strip()
        if raw_quota == "":
            quota = None
        elif raw_quota.isdigit():
            quota = int(raw_quota)
        else:
            return redirect("/panel/#users")
    profile.entitlement_quota = quota
    profile.save(update_fields=["entitlement_quota", "updated_at"])
    log_event(None, "ACCOUNT_LIMIT_UPDATED", f"user={target.username} limit={quota}", request=request)
    return redirect("/panel/#users")


@staff_member_required
@require_POST
def panel_delete_account(request, account_id):
    if not user_has_perm(request.user, "accounts.manage"):
        return HttpResponseForbidden("Missing permission: accounts.manage")
    target = get_object_or_404(get_user_model(), pk=account_id)
    if not can_manage_account(request.user, target):
        return HttpResponseForbidden("Account is outside your ownership boundary.")
    if target.pk == request.user.pk or (target.is_superuser and not request.user.is_superuser):
        return HttpResponseForbidden("Cannot delete this account.")
    _, msg = delete_or_disable_account(request.user, target, request=request)
    request.session["panel_msg"] = msg
    return redirect("/panel/#users")


@staff_member_required
@require_POST
def panel_toggle_account(request, account_id):
    if not user_has_perm(request.user, "accounts.manage"):
        return HttpResponseForbidden("Missing permission: accounts.manage")
    target = get_object_or_404(get_user_model(), pk=account_id)
    if not can_manage_account(request.user, target):
        return HttpResponseForbidden("Account is outside your ownership boundary.")
    if target.pk == request.user.pk or (target.is_superuser and not request.user.is_superuser):
        return HttpResponseForbidden("Cannot deactivate this account.")
    set_account_active(request.user, target, not target.is_active, request=request)
    return redirect("/panel/#users")


@staff_member_required
@require_POST
def panel_create_enrollment(request):
    if not user_has_perm(request.user, "enrollments.manage"):
        return HttpResponseForbidden("Missing permission: enrollments.manage")
    su, retailer, vendor = get_ownership_context_for_creator(request.user)
    cust_name = request.POST.get("customer_name", "").strip()
    cust_mobile = request.POST.get("customer_mobile", "").strip()
    cust_email = request.POST.get("customer_email", "").strip()
    brand = request.POST.get("brand", "").strip()
    model = request.POST.get("model", "").strip()
    imei = request.POST.get("imei", "").strip()
    android_version = request.POST.get("android_version", "").strip() or "14"
    intended_id = request.POST.get("intended_device_identifier", "").strip()
    try:
        major = int(android_version.split(".")[0])
    except ValueError:
        major = 14
    method = Device.EnrollmentMethod.ADB_16 if major >= 16 else Device.EnrollmentMethod.QR_9_15
    reg_ref = f"REG-{uuid.uuid4().hex[:8].upper()}"

    customer = None
    if cust_name or cust_mobile or cust_email:
        customer = Customer(
            full_name=cust_name or cust_mobile or cust_email,
            retailer=retailer,
            vendor=vendor,
            registered_by_account=request.user,
        )
        if cust_mobile:
            customer.set_mobile(cust_mobile)
        if cust_email:
            customer.set_email(cust_email)
        customer.save()

    pending_dev = None
    if brand or model or imei or request.POST.get("android_version"):
        pending_dev = Device(
            device_identifier=f"pending-{uuid.uuid4().hex[:16]}",
            registration_reference=reg_ref,
            manufacturer=brand,
            model=model,
            android_version=android_version,
            enrollment_method=method,
            enrollment_status=Device.Enrollment.PENDING,
            ownership_status=Device.OwnershipStatus.ACTIVE,
            customer=customer,
            superuser=su,
            retailer=retailer,
            vendor=vendor,
            original_retailer=retailer,
            original_vendor=vendor,
            registered_by_account=request.user,
        )
        if imei:
            pending_dev.set_imei(imei)
        pending_dev.auth_token_hash = Device.hash_token(secrets.token_urlsafe(32))
        pending_dev.save()

    session, raw_token = EnrollmentSession.create_session(
        created_by=request.user,
        superuser=su,
        retailer=retailer,
        vendor=vendor,
        customer=customer,
        intended_device_identifier=intended_id,
        enrollment_method=method,
        registration_reference=reg_ref,
        pending_device=pending_dev,
    )
    log_event(None, "ENROLLMENT_SESSION_CREATED", f"session={session.id}", request=request)
    request.session["new_enrollment_token"] = raw_token
    request.session["new_enrollment_id"] = str(session.id)
    return redirect("/panel/#enrollments")


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


def provisioning_payload(base_url: str | None = None, enrollment_key: str | None = None) -> dict:
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
            "enrollment_key": enrollment_key if enrollment_key is not None else settings.ENROLLMENT_KEY,
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
    session_id = request.GET.get("session_id")
    session_key = None
    if session_id:
        session = get_object_or_404(EnrollmentSession, pk=session_id)
        if not can_access_enrollment(request.user, session):
            return HttpResponseForbidden("Enrollment session is outside your ownership boundary.")
        if not session.is_usable:
            return HttpResponse("Enrollment session already used or expired. Create a new one.", status=409)
        session_key = session.get_raw_token()
        if not session_key:
            return HttpResponse("Enrollment session already used or expired. Create a new one.", status=409)
    elif not is_superuser_account(request.user):
        # The platform-wide static enrollment key must never be exposed to retailers/vendors.
        return HttpResponseForbidden("Create an enrollment session first (Enrollments tab).")
    if not settings.APK_CERT_SHA256:
        return HttpResponse("APK certificate checksum not configured (AKDL_APK_CERT_SHA256).", status=503)
    req_base = request.GET.get("base_url") or (
        f"{request.scheme}://{request.get_host()}" if settings.PUBLIC_BASE_URL == "auto" else settings.PUBLIC_BASE_URL
    )
    payload_dict = provisioning_payload(req_base, enrollment_key=session_key)
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
