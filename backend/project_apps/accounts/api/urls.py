from django.urls import path

from project_apps.accounts.api.views import UserRegistrationView
urlpatterns = [
    path('register',UserRegistrationView.as_view(),name='registration'),
    
]




