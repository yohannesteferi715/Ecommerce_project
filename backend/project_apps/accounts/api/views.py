from django.contrib.auth import authenticate, get_user_model
from django.conf import settings

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

# R3 FIX: RefreshToken was imported twice; consolidated into one import
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from project_apps.accounts.api.serializers import UserRegistrationSerializer


class UserRegistrationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "email": serializer.instance.email,
                    "full_name": serializer.instance.full_name,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"detail": "Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=email, password=password)

        if user is None:
            return Response(
                {"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED
            )
        if not user.is_active:
            return Response(
                {"detail": "Account is inactive."}, status=status.HTTP_403_FORBIDDEN
            )

        refresh = RefreshToken.for_user(user)
        access_token = refresh.access_token
        secure = not settings.DEBUG

        response = Response(
            {
                "message": "Login successful",
                "user": {
                    "email": user.email,
                    "full_name": user.full_name,
                },
            },
            status=status.HTTP_200_OK,
        )
        response.set_cookie(
            key="access_token",
            value=str(access_token),
            httponly=True,
            secure=secure,
            samesite="Lax",
            max_age=60 * 15,
        )
        response.set_cookie(
            key="refresh_token",
            value=str(refresh),
            httponly=True,
            secure=secure,
            samesite="Lax",
            max_age=60 * 60 * 24 * 7,
        )
        return response


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({"email": user.email, "full_name": user.full_name})


class RefreshTokenView(APIView):
    """
    Refresh the access token using the refresh_token stored in the HttpOnly cookie.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token_str = request.COOKIES.get("refresh_token")
        if not refresh_token_str:
            return Response(
                {"detail": "No refresh token found."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            token = RefreshToken(refresh_token_str)

            # B7 FIX: derive the new refresh token from the validated token itself,
            # not from request.user (which is AnonymousUser at this point because
            # the old access token is expired and cookie auth returns None).
            if settings.SIMPLE_JWT.get("ROTATE_REFRESH_TOKENS", True):
                try:
                    token.blacklist()
                except AttributeError:
                    pass
                # Build a new refresh token for the user encoded in the old token
                User = get_user_model()
                user = User.objects.get(pk=token['user_id'])
                new_refresh = RefreshToken.for_user(user)
            else:
                new_refresh = token

            access_token = new_refresh.access_token
            secure = not settings.DEBUG

            response = Response({"message": "Token refreshed"}, status=status.HTTP_200_OK)
            response.set_cookie(
                "access_token",
                str(access_token),
                httponly=True,
                secure=secure,
                samesite="Lax",
                max_age=60 * 15,
                path="/",
            )
            response.set_cookie(
                "refresh_token",
                str(new_refresh),
                httponly=True,
                secure=secure,
                samesite="Lax",
                max_age=60 * 60 * 24 * 7,
                path="/",
            )
            return response

        except TokenError:
            return Response(
                {"detail": "Invalid or expired refresh token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # B8 FIX: read cookie before building the response (delete_cookie only
        # sets a header; it does not clear request.COOKIES).
        # Also replaced bare except with specific TokenError catch.
        refresh_token_str = request.COOKIES.get("refresh_token")

        response = Response({"message": "Logged out"}, status=status.HTTP_200_OK)
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/")

        if refresh_token_str:
            try:
                token = RefreshToken(refresh_token_str)
                token.blacklist()
            except TokenError:
                pass

        return response
