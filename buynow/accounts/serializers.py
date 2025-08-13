from rest_framework import serializers
from .models import User
from django.contrib.auth.hashers import make_password
from django.conf import settings
import jwt
import os,json
import datetime
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.exceptions import ImproperlyConfigured
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
secret_file = os.path.join(BASE_DIR, 'secrets.json') 

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

# 구글 소셜 로그인 시리얼라이저
class GoogleLoginSerializer(serializers.Serializer):
    admin_password = serializers.CharField(write_only=True, required=True)
    id_token = serializers.CharField(write_only=True, required=True)
    user_role = serializers.CharField(required=False)

    # 검증 후 토큰 발급
    def create(self, validated_data):
        # firebase 토큰 검증
        from config.authentication import verify_firebase_id_token
        email, image_url = verify_firebase_id_token(validated_data['id_token'])
        role = validated_data.get('user_role', 'customer')

        user, created = User.objects.get_or_create(
            user_email=email,
            defaults={
                'user_image_url': image_url,
                'user_role': role,
                # 비밀번호 없이 "" 저장하지만 해싱
                'user_password': make_password("")
            }
        )

        # JWT Access & Refresh Token 발급
        access_token, refresh_token = self._generate_tokens(user)

        return {
            "user": user,
            "created": created,
            "access_token": access_token,
            "refresh_token": refresh_token
        }

    def _generate_tokens(self, user):
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token), str(refresh)

# 관리자 로그인용 시리얼라이저
class AdminLoginSerializer(serializers.Serializer):
    admin_email = serializers.CharField(required=True)
    admin_password = serializers.CharField(write_only=True, required = True)
    user_password = serializers.CharField(required=True)
    user_role = serializers.CharField(required = True)

    """class Meta:
        model = User

        fields = ['admin_password','user_password','user_role']"""

    def validate(self, attrs):
        role = attrs.get('user_role')
        password = attrs.get('admin_password')
        if role != 'admin':
            raise serializers.ValidationError("관리자 로그인을 위해 user_role은 'admin'이어야 합니다.")
        
        if password != ADMIN_PASSWORD:
            raise serializers.ValidationError("관리자 비밀번호가 일치하지 않습니다.")
        return attrs
        
    def create(self,validated_data):
        user_password = make_password(validated_data['user_password'])
        user, created = User.objects.get_or_create(
            user_email = validated_data['admin_email'],
            defaults={
                'user_role' : 'admin',
                'user_password' : user_password
            }
        )

        # JWT Access & Refresh Token 발급
        access_token, refresh_token = self._generate_tokens(user)

        return {
            "user": user,
            "created": created,
            "access_token": access_token,
            "refresh_token": refresh_token
        }
    
    def _generate_tokens(self,user):
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token), str(refresh)
