from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from project_apps.accounts.api.serializers import UserRegistrationSerializer
from rest_framework import status



from rest_framework.permissions import AllowAny
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
class UserRegistrationView(APIView):

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
    
    
    
    
class  LoginView(APIView):
    
    permission_classes=[AllowAny]
    
    def post(self,request):
        
        email=request.data.get('email')
        password=request.data.get('password')
        
        if not email or not password :
            
            return Response(
                {
                    "detail":"Email and password are required."
                },status=status.HTTP_400_BAD_REQUEST
            )
        user=authenticate(request,email=email,password=password)
        
        if user is None:
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED
                
            )
        if not user.is_active:
            return Response (
                {
                    "detail": "Account is inactive."
                }
                ,status=status.HTTP_403_FORBIDDEN
            )
        refresh=RefreshToken.for_user(user)
        access_token = refresh.access_token
        
        response=Response(
            
             {
                "message": "Login successful",
                "user": {
                    "email": user.email,
                    "full_name": user.full_name,
                }
            },
            status=status.HTTP_200_OK
        )
        
        response.set_cookie(
            key="access_token",
            value=str(access_token),
            httponly=True,
            secure=False,      # IMPORTANT for dev
            samesite="Lax",
            max_age=60 * 15
        )
        response.set_cookie(
            key="refresh_token",
            value=str(refresh),
            httponly=True,
            secure=False,      # IMPORTANT for dev
            samesite="Lax",
            max_age=60 * 60 * 24 * 7
        )
        
        return response
    
    
    
    

