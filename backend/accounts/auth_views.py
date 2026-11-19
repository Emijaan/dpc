"""JWT authentication endpoints: login, refresh (rotating), logout (blacklist), me."""
from django.db import connection
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from audit.models import log_event
from devices.ownership import get_account_type
from roles.permissions import get_user_permissions


def user_payload(user) -> dict:
    profile = getattr(user, "profile", None)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "account_type": get_account_type(user),
        "retailer_id": profile.retailer_id if profile else None,
        "permissions": sorted(get_user_permissions(user)),
    }


class LoginSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["account_type"] = get_account_type(user)  # informational only; the backend re-checks on every request
        return token


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        s = LoginSerializer(data=request.data, context={"request": request})
        try:
            s.is_valid(raise_exception=True)
        except Exception:
            # Same response for unknown user / wrong password / inactive account: no account enumeration.
            attempted = str(request.data.get("username", ""))[:64] if hasattr(request.data, "get") else ""
            log_event(None, "LOGIN_FAILED", f"username={attempted}", request=request)
            return Response({"error": "invalid_credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        user = s.user
        log_event(None, "LOGIN_SUCCESS", f"user={user.username}", actor=user, request=request)
        return Response({**s.validated_data, "user": user_payload(user)})


class RefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "refresh"

    def post(self, request):
        s = TokenRefreshSerializer(data=request.data)
        try:
            s.is_valid(raise_exception=True)
        except Exception:
            # Expired, blacklisted (already rotated / reused), malformed or deactivated user.
            log_event(None, "TOKEN_REFRESH_REJECTED", "", request=request)
            return Response({"error": "invalid_refresh_token"}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(s.validated_data)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = LogoutSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            token = RefreshToken(s.validated_data["refresh"])
        except TokenError:
            return Response({"error": "invalid_refresh_token"}, status=status.HTTP_400_BAD_REQUEST)
        if str(token.get("user_id")) != str(request.user.pk):
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            token.blacklist()
        except TokenError:
            pass
        log_event(None, "LOGOUT", f"user={request.user.username}", request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(user_payload(request.user))


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT 1")
            return Response({"status": "ok"})
        except Exception:
            return Response({"status": "degraded"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
