from django.urls import path, include
from .views import UserRegistrationView, LoginView, LogoutView, RefreshTokenView, CurrentUserView
from .oauth_views import GoogleLogin, OAuthSuccessView, OAuthCurrentUserView

urlpatterns = [
    # Normal JWT auth
    path('register/', UserRegistrationView.as_view(), name='registration'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('refresh_token/', RefreshTokenView.as_view(), name='refreshtoken'),
    path('current_user/', CurrentUserView.as_view(), name='current_user'),

    # DJ-Rest-Auth endpoints
    path('dj-rest-auth/', include('dj_rest_auth.urls')),
    path('dj-rest-auth/registration/', include('dj_rest_auth.registration.urls')),

    # Custom Social login + JWT endpoints
    path('google-login/', GoogleLogin.as_view(), name='google_login'),
    path('oauth-success/', OAuthSuccessView.as_view(), name='oauth_success'),
    path('oauth-current-user/', OAuthCurrentUserView.as_view(), name='oauth_current_user'),
]