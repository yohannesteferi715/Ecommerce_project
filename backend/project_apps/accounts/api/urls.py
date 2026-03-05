from django.urls import path

from project_apps.accounts.api.views import ( UserRegistrationView,
                                             
LoginView,LogoutView,RefreshTokenView,CurrentUserView)
urlpatterns = [
    path('register',UserRegistrationView.as_view(),name='registration'),
    path('login',LoginView.as_view(),name='login'),
    path('logout',LogoutView.as_view(),name='logout'),
    path('refresh_tokens',RefreshTokenView.as_view(),name='refreshtoken'),
    path('current_user',CurrentUserView.as_view(),name='current_user')
    
]




