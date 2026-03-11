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
