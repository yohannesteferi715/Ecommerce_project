from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response

from project_apps.accounts.api.serializers import UserRegistrationSerializer
from rest_framework import status


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
