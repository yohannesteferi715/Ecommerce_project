from rest_framework import serializers
from project_apps.accounts.models import CustomUser

from django.contrib.auth import get_user_model
from rest_framework.validators import UniqueValidator




class UserRegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        validators=[
            UniqueValidator(
                queryset=get_user_model().objects.all(),
                message="User with this account already exists.",
            )
        ]
    )
    password = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model =get_user_model()
        fields = ["full_name", "email", "password", "password2"]

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:

            raise serializers.ValidationError({"password": "Passwords do not match."})

        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        password2 = validated_data.pop("password2")

        user = CustomUser.objects.create(**validated_data)

        user.set_password(password)

        user.save()

        return user
