from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import log_event
from roles.models import AccountRole, Role
from roles.permissions import HasPermissionCode, ensure_default_rbac


class AccountCreateSerializer(serializers.Serializer):
    username = serializers.RegexField(r"^[A-Za-z0-9_.\-@]{3,64}$")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    password = serializers.CharField(min_length=8, max_length=128)
    role_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)


class AccountListCreateView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "accounts.manage"

    def get(self, request):
        U = get_user_model()
        items = []
        for u in U.objects.all().order_by("id"):
            rnames = list(u.account_roles.values_list("role__name", flat=True))
            items.append({
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "is_active": u.is_active,
                "is_superuser": u.is_superuser,
                "roles": rnames,
            })
        return Response({"accounts": items})

    def post(self, request):
        ensure_default_rbac()
        s = AccountCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        U = get_user_model()
        if U.objects.filter(username=d["username"]).exists():
            return Response({"error": "username_exists"}, status=status.HTTP_409_CONFLICT)
        roles = list(Role.objects.filter(id__in=d["role_ids"]))
        if any(r.name == "SUPER_ADMIN" for r in roles) and not request.user.is_superuser:
            return Response({"error": "cannot_create_super_admin"}, status=status.HTTP_403_FORBIDDEN)
        user = U.objects.create_user(
            username=d["username"], email=d["email"], password=d["password"], is_staff=True
        )
        for r in roles:
            AccountRole.objects.create(user=user, role=r, assigned_by=request.user)
        log_event(None, "ACCOUNT_CREATED", f"user={user.username}", request=request)
        return Response(
            {"id": user.id, "username": user.username, "is_active": user.is_active},
            status=status.HTTP_201_CREATED,
        )


class AccountStatusView(APIView):
    permission_classes = [HasPermissionCode]
    required_permission = "accounts.manage"

    def post(self, request, account_id):
        target = get_object_or_404(get_user_model(), pk=account_id)
        if target.is_superuser and not request.user.is_superuser:
            return Response({"error": "cannot_modify_super_admin"}, status=status.HTTP_403_FORBIDDEN)
        active = bool(request.data.get("is_active", True))
        target.is_active = active
        target.save(update_fields=["is_active"])
        log_event(None, "ACCOUNT_STATUS_CHANGED", f"user={target.username} active={active}", request=request)
        return Response({"id": target.id, "username": target.username, "is_active": target.is_active})
