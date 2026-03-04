from django.urls import path

from project_apps.accounts.api.views import ( UserRegistrationView,
                                             
LoginView)
urlpatterns = [
    path('register',UserRegistrationView.as_view(),name='registration'),
    path('login',LoginView.as_view(),name='login')
    
]




