from django.db import models
from  django.contrib.auth.models import AbstractUser
# Create your models here.
class CustomUser(AbstractUser):
    email=models.EmailField(unique=True)
    USERNAME_FIELD='email'
    full_name=models.CharField(max_length=30)
    REQUIRED_FIELDS = []
    
    def __str__(self):
        return self.email
    