import uuid
from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.contrib.auth.hashers import make_password


class UserManager(BaseUserManager):
    def create_user(self, user_email, password=None, **extra_fields):
        if not user_email:
            raise ValueError("Email은 필수입니다.")
        user = self.model(user_email=self.normalize_email(user_email), **extra_fields)
        user.user_password = make_password(password) if password else ""
        user.save(using=self._db)
        return user

    def create_superuser(self, user_email, password, **extra_fields):
        extra_fields.setdefault("user_role", "admin")
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(user_email, password, **extra_fields)


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    ROLE_CHOICES = (
        ("admin", "Admin"),
        ("customer", "Customer"),
        ("owner", "Owner"),
    )

    id = models.BigAutoField(primary_key=True)
    user_email = models.EmailField(unique=True)
    user_image_url = models.TextField(blank=True)
    user_password = models.CharField(max_length=128, default="")
    user_role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, default="customer"
    )
    user_address = models.CharField(blank=True, max_length=100)
    user_discounted_cost_sum = models.IntegerField(default=0)
    is_dummy = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)  # 관리자 사이트 접근용
    is_active = models.BooleanField(default=True)

    objects = UserManager()

    USERNAME_FIELD = "user_email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return f"{self.user_email} ({self.user_role})"
