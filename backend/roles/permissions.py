from rest_framework import permissions

from roles.models import AccountRole, Permission, Role

PERMISSION_DEFINITIONS = {
    "devices.view": "View registered devices and status",
    "devices.lock": "Issue DEVICE_LOCK commands",
    "devices.unlock": "Issue DEVICE_UNLOCK commands",
    "devices.sync": "Issue DEVICE_SYNC / DEVICE_STATUS commands",
    "devices.release": "Issue DEVICE_RELEASE commands",
    "commands.view": "View command history and results",
    "roles.manage": "Create/edit roles, assign/revoke permissions, assign user roles",
    "accounts.manage": "Create and activate/deactivate operator accounts",
    "keys.view": "View public keys and key metadata",
    "keys.manage": "Generate, rotate, and revoke signing keys",
    "audit.view": "View security and command audit logs",
}

DEFAULT_ROLES = {
    "SUPER_ADMIN": list(PERMISSION_DEFINITIONS.keys()),
    "ADMIN": [
        "devices.view", "devices.lock", "devices.unlock", "devices.sync",
        "commands.view", "keys.view", "audit.view",
    ],
    "OPERATOR": [
        "devices.view", "devices.lock", "devices.unlock", "devices.sync", "commands.view",
    ],
    "VIEWER": [
        "devices.view", "commands.view",
    ],
}


def ensure_default_rbac():
    """Idempotently seeds permissions and the four initial roles."""
    perms = {}
    for code, desc in PERMISSION_DEFINITIONS.items():
        p, _ = Permission.objects.get_or_create(code=code, defaults={"description": desc})
        perms[code] = p
    for role_name, codes in DEFAULT_ROLES.items():
        role, created = Role.objects.get_or_create(
            name=role_name, defaults={"description": f"System {role_name} role", "is_system": True}
        )
        if created or not role.permissions.exists():
            role.permissions.set([perms[c] for c in codes])


def get_user_permissions(user) -> set[str]:
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return set()
    if getattr(user, "is_superuser", False):
        return set(PERMISSION_DEFINITIONS.keys())
    return set(
        Permission.objects.filter(roles__assignments__user=user).values_list("code", flat=True)
    )


def user_has_perm(user, code: str) -> bool:
    """Deny-by-default authorization check independent of role names."""
    return code in get_user_permissions(user)


class HasPermissionCode(permissions.BasePermission):
    """DRF permission enforcing a specific permission code on operator endpoints."""

    def __init__(self, code: str | None = None):
        self.code = code

    def has_permission(self, request, view):
        required = self.code or getattr(view, "required_permission", None)
        if not required:
            return False
        return user_has_perm(request.user, required)

