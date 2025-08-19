from rest_framework import serializers
from .models import User
from django.contrib.auth.hashers import make_password
from rest_framework_simplejwt.tokens import RefreshToken
from config.authentication import verify_firebase_id_token
from django.conf import settings
import os, json
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth.hashers import check_password

BASE_DIR = Path(__file__).resolve().parent.parent

secret_file = os.path.join(BASE_DIR, "secrets.json")

with open(secret_file) as f:
    secrets = json.loads(f.read())


def get_secret(setting, secrets=secrets):
    # secret 변수를 가져오거나 그렇지 못 하면 예외를 반환
    try:
        return secrets[setting]
    except KeyError:
        error_msg = "Set the {} environment variable".format(setting)
        raise ImproperlyConfigured(error_msg)


ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD")


class GoogleLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField(write_only=True)
    user_role = serializers.CharField(required=False)

    def create(self, validated_data):
        email, image_url = verify_firebase_id_token(validated_data["id_token"])
        role = validated_data.get("user_role", "customer")

        user, created = User.objects.get_or_create(
            user_email=email,
            defaults={
                "user_image_url": image_url,
                "user_role": role,
                "password": make_password(""),
            },
        )

        access_token, refresh_token = self._generate_tokens(user)
        return {
            "user": user,
            "created": created,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    def _generate_tokens(self, user):
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token), str(refresh)


class AdminLoginSerializer(serializers.Serializer):
    admin_email = serializers.CharField()
    admin_password = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)
    user_role = serializers.CharField()

    def validate(self, attrs):
        if attrs.get("user_role") != "admin":
            raise serializers.ValidationError("user_role은 'admin'이어야 합니다.")
        if attrs.get("admin_password") != ADMIN_PASSWORD:
            raise serializers.ValidationError("관리자 비밀번호 불일치")
        return attrs

    def create(self, validated_data):
        password = make_password(validated_data["password"])
        user, created = User.objects.get_or_create(
            user_email=validated_data["admin_email"],
            defaults={
                "user_role": "admin",
                "password": password,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        access_token, refresh_token = self._generate_tokens(user)
        return {
            "user": user,
            "created": created,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    def _generate_tokens(self, user):
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token), str(refresh)

# 공급자 회원가입/로그인 관련 시리얼라이저
class OwnerLoginSerializer(serializers.Serializer):
    owner_email = serializers.CharField()
    owner_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("owner_email")
        password = attrs.get("owner_password")
        try :
            user = User.objects.get(user_email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"detail" : "이메일 또는 비밀번호가 올바르지 않습니다."})
        
        if not check_password(password, user.password):
            raise serializers.ValidationError({"detail" : "이메일 또는 비밀번호가 올바르지 않습니다."})

        if user.user_role != "owner":
            raise serializers.ValidationError({"detail" : "공급자 계정이 아닙니다."})

        access_token, refresh_token = self._generate_tokens(user)
        return {
            "user": user,
            "user_id" : user.id,
            "user_email" : user.user_email,
            "user_role" : "owner",
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    def _generate_tokens(self, user):
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token), str(refresh)


# User API 관련 시리얼라이저 --------------------------------------------
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "user_email",
            "user_image_url",
            "user_role",
            "user_address",
            "user_discounted_cost_sum",
            "created_at",
            "updated_at",
            "is_dummy",
        ]
