from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import log_event
from devices.ownership import can_manage_account
from roles.models import AccountRole, Permission, Role
from roles.permissions import HasPermissionCode, ensure_default_rbac


def role_dict(r: Role) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "is_system": r.is_system,
        "permissions": list(r.permissions.values_list("code", flat=True)),
    }


class RoleCreateSerializer(serializers.Serializer):
    name = serializers.RegexField(r"^[A-Za-z0-9_\- ]{2,64}$")
    description = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    permissions = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class RoleListCreateView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "roles.manage"

    def get(self, request):
        ensure_default_rbac()
        return Response({"roles": [role_dict(r) for r in Role.objects.prefetch_related("permissions")]})

    def post(self, request):
        ensure_default_rbac()
        s = RoleCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if Role.objects.filter(name=d["name"]).exists():
            return Response({"error": "role_exists"}, status=status.HTTP_409_CONFLICT)
        role = Role.objects.create(name=d["name"], description=d["description"], is_system=False)
        if d["permissions"]:
            perms = list(Permission.objects.filter(code__in=d["permissions"]))
            role.permissions.set(perms)
        log_event(None, "ROLE_CREATED", f"role={role.name} perms={len(d['permissions'])}", request=request)
        return Response(role_dict(role), status=status.HTTP_201_CREATED)


class RoleDetailView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "roles.manage"

    def put(self, request, role_id):
        role = get_object_or_404(Role, pk=role_id)
        if role.name == "SUPER_ADMIN":
            return Response({"error": "cannot_modify_super_admin"}, status=status.HTTP_403_FORBIDDEN)
        s = RoleCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if not role.is_system:
            role.name = d["name"]
        role.description = d["description"]
        role.save()
        if "permissions" in request.data:
            role.permissions.set(Permission.objects.filter(code__in=d["permissions"]))
        log_event(None, "ROLE_UPDATED", f"role={role.name}", request=request)
        return Response(role_dict(role))

    def delete(self, request, role_id):
        role = get_object_or_404(Role, pk=role_id)
        if role.is_system:
            return Response({"error": "cannot_delete_system_role"}, status=status.HTTP_403_FORBIDDEN)
        name = role.name
        role.delete()
        log_event(None, "ROLE_DELETED", f"role={name}", request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RolePermissionsSerializer(serializers.Serializer):
    grant = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    revoke = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class RolePermissionsView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "roles.manage"

    def post(self, request, role_id):
        ensure_default_rbac()
        role = get_object_or_404(Role, pk=role_id)
        if role.name == "SUPER_ADMIN":
            return Response({"error": "cannot_modify_super_admin"}, status=status.HTTP_403_FORBIDDEN)
        s = RolePermissionsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if d["grant"]:
            role.permissions.add(*Permission.objects.filter(code__in=d["grant"]))
        if d["revoke"]:
            role.permissions.remove(*Permission.objects.filter(code__in=d["revoke"]))
        log_event(
            None,
            "ROLE_PERMISSIONS_CHANGED",
            f"role={role.name} grant={d['grant']} revoke={d['revoke']}",
            request=request,
        )
        return Response(role_dict(role))


class AccountRoleAssignSerializer(serializers.Serializer):
    role_ids = serializers.ListField(child=serializers.IntegerField(), required=True)


class AccountRolesView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "roles.manage"

    def post(self, request, account_id):
        ensure_default_rbac()
        target = get_object_or_404(get_user_model(), pk=account_id)
        if not can_manage_account(request.user, target):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        s = AccountRoleAssignSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        roles = list(Role.objects.filter(id__in=s.validated_data["role_ids"]))
        if any(r.name == "SUPER_ADMIN" for r in roles) and not request.user.is_superuser:
            return Response({"error": "only_super_admin_can_assign_super_admin"}, status=status.HTTP_403_FORBIDDEN)
        AccountRole.objects.filter(user=target).delete()
        for r in roles:
            AccountRole.objects.create(user=target, role=r, assigned_by=request.user)
        names = [r.name for r in roles]
        log_event(None, "ACCOUNT_ROLES_ASSIGNED", f"user={target.username} roles={names}", request=request)
        return Response({"account_id": target.id, "username": target.username, "roles": names})
