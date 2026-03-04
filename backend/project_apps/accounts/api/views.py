from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from project_apps.accounts.api.serializers import UserRegistrationSerializer
from rest_framework import status




from rest_framework.permissions import AllowAny,IsAuthenticated
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken

from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from django.conf import settings
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
        user=authenticate(request,username=email,password=password)
        
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
        secure = not settings.DEBUG
        response.set_cookie(
            key="access_token",
            value=str(access_token),
            httponly=True,
            secure=secure,      # IMPORTANT for dev
            samesite="Lax",
            max_age=60 * 15
        )
        response.set_cookie(
            key="refresh_token",
            value=str(refresh),
            httponly=True,
            secure=secure,      # IMPORTANT for dev
            samesite="Lax",
            max_age=60 * 60 * 24 * 7
        )
        
        return response
    
    
class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "email": user.email,
            "full_name": user.full_name,
        })






class RefreshTokenView(APIView):
    """
    Refresh the access token using the refresh_token stored in HttpOnly cookie.
 
    """
    def post(self, request):
        # Get refresh token from cookie
        refresh_token = request.COOKIES.get("refresh_token")
        if not refresh_token:
            return Response({"detail": "No refresh token found."}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            # Validate refresh token
            token = RefreshToken(refresh_token)

            # Generate new access token
            access_token = token.access_token

            # rotate refresh token
            if getattr(settings, "SIMPLE_JWT", {}).get("ROTATE_REFRESH_TOKENS", True):
                # Blacklist old refresh token
                try:
                    token.blacklist()
                except AttributeError:
                    pass  
                new_refresh = RefreshToken.for_user(request.user)
            else:
                new_refresh = token

            # Set cookies
            secure = not settings.DEBUG
            response = Response({"message": "Token refreshed"}, status=status.HTTP_200_OK)
            response.set_cookie(
                "access_token",
                str(access_token),
                httponly=True,
                secure=secure,
                samesite="Lax" if settings.DEBUG else "None",
                max_age=60*15,  # 15 minutes
                path="/",
            )
            response.set_cookie(
                "refresh_token",
                str(new_refresh),
                httponly=True,
                secure=secure,
                samesite="Lax" if settings.DEBUG else "None",
                max_age=60*60*24*7,  # 7 days
                path="/",
            )

            return response

        except TokenError:
            return Response({"detail": "Invalid or expired refresh token"}, status=status.HTTP_401_UNAUTHORIZED)
        

