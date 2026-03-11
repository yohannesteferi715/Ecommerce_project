# accounts/api/oauth_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView


# -------------------------------
# 1. Google OAuth login view
# -------------------------------
class GoogleLogin(SocialLoginView):
    """
    Login with Google OAuth2.

    Receives a Google authorization code from the frontend, exchanges it
    for an access token, fetches user info, and returns a DRF token or JWT.

    POST body:
        - code: Google authorization code
        - client_id: Your Google OAuth client ID
        - redirect_uri: Frontend redirect URL registered in Google Cloud

    Response (JSON):
        - key: DRF token
        OR
        - access & refresh: JWT tokens
    """
    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client
    permission_classes = [AllowAny]


# -------------------------------
# 2. Custom endpoint to issue JWT cookies after OAuth login
#    (called by frontend after SocialLoginView succeeds)
# -------------------------------
class OAuthSuccessView(APIView):
    """
Handle successful OAuth login.

Ensures the user is authenticated after OAuth, generates JWT access and
refresh tokens using SimpleJWT, and stores them in secure HTTP-only cookies.
Returns basic user information in the response.
"""
    
    permission_classes = [AllowAny]

    def post(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response(
                {"detail": "User not authenticated"}, status=status.HTTP_401_UNAUTHORIZED
            )

        refresh = RefreshToken.for_user(user)
        access = refresh.access_token

        secure = not settings.DEBUG

        response = Response(
            {
                "message": "OAuth login successful",
                "user": {
                    "email": user.email,
                    "full_name": getattr(user, "full_name", ""),
                },
            },
            status=status.HTTP_200_OK,
        )

        # Set JWT cookies
        response.set_cookie(
            "access_token",
            str(access),
            httponly=True,
            secure=secure,
            samesite="Lax",
            max_age=60 * 15,  # 15 min
        )
        response.set_cookie(
            "refresh_token",
            str(refresh),
            httponly=True,
            secure=secure,
            samesite="Lax",
            max_age=60 * 60 * 24 * 7,  # 7 days
        )

        return response


# -------------------------------
# 3. Current user info (OAuth users)
# -------------------------------
class OAuthCurrentUserView(APIView):

    permission_classes = [AllowAny]

    def get(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response(
                {"detail": "User not authenticated"}, status=status.HTTP_401_UNAUTHORIZED
            )

        return Response(
            {
                "email": user.email,
                "full_name": getattr(user, "full_name", ""),
            },
            status=status.HTTP_200_OK,
        )