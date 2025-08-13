from django.shortcuts import render
from rest_framework.decorators import api_view,permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from config.authentication import FirebaseIDTokenAuthentication

from .models import User
from .serializers import *

import uuid
#import jwt

from .serializers import GoogleLoginSerializer, AdminLoginSerializer

from rest_framework.permissions import BasePermission

class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.user_role == 'admin'

class IsUserRole(BasePermission):
    allowed_roles = ['admin', 'customer']

    def has_permission(self, request, view):
        return request.user and request.user.user_role in self.allowed_roles


class IsOwnerRole(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.user_role == 'owner'

# Create your views here.


# 로그인 & 토큰 관련 view ------------------------------------
# 구글 로그인 기능 (Firebase 토큰 받아 사용자 생성or로그인)
class GoogleLoginAPIView(APIView):
    authentication_classes = [FirebaseIDTokenAuthentication]
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Google 로그인",
        operation_description="Firebase에서 받은 id_token으로 로그인/회원가입 처리 후 JWT 토큰 반환",
        request_body=GoogleLoginSerializer,
        responses={
            200: openapi.Response(
                description="로그인/회원가입 성공",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "message": openapi.Schema(type=openapi.TYPE_STRING),
                        "user_email": openapi.Schema(type=openapi.TYPE_STRING),
                        "user_image_url": openapi.Schema(type=openapi.TYPE_STRING),
                        "user_role": openapi.Schema(type=openapi.TYPE_STRING),
                        "access_token": openapi.Schema(type=openapi.TYPE_STRING),
                        "refresh_token": openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            ),
            400: "유효하지 않은 요청 (id_token 누락 등)"
        }
    )
    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        user = result["user"]
        created = result["created"]
        message = "회원가입 성공" if created else "로그인 성공"

        res = Response(
            {
                "message": message,
                "user_email": user.user_email,
                "user_image_url": user.user_image_url,
                "user_role": user.user_role,
                "access_token": result["access_token"],
                "refresh_token": result["refresh_token"]
            },
            status=status.HTTP_200_OK
        )

        # 쿠키 저장
        #res.set_cookie("access_token", result["access_token"], httponly=True, secure=True, samesite="Strict")
        #res.set_cookie("refresh_token", result["refresh_token"], httponly=True, secure=True, samesite="Strict")

        return res
    
# admin 로그인 기능
class AdminLoginAPIView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Admin 로그인",
        operation_description="관리자 로그인/회원가입 처리 후 JWT 토큰 반환",
        request_body=AdminLoginSerializer,
        responses={
            200: openapi.Response(
                description="로그인/회원가입 성공",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "message": openapi.Schema(type=openapi.TYPE_STRING),
                        "user_role": openapi.Schema(type=openapi.TYPE_STRING),
                        "access_token": openapi.Schema(type=openapi.TYPE_STRING),
                        "refresh_token": openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            ),
            400: "유효하지 않은 요청 (누락 등)",
            403: "관리자 권한 없음(password 불일치)"
        }
    )
    def post(self,request):
        serializer = AdminLoginSerializer(data = request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        user = result["user"]
        created = result["created"]
        message = "회원가입 성공" if created else "로그인 성공"

        res = Response(
            {
                "message": message,
                "user_role": user.user_role,
                "access_token": result["access_token"],
                "refresh_token": result["refresh_token"]
            },
            status=status.HTTP_200_OK
        )

        # 쿠키 저장
        #res.set_cookie("access_token", result["access_token"], httponly=True, secure=True, samesite="Strict")
        #res.set_cookie("refresh_token", result["refresh_token"], httponly=True, secure=True, samesite="Strict")

        return res

# 공급자 로그인 기능

# refresh로 access 토큰 재발급
class TokenRefreshAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh_token")
        if not refresh_token:
            return Response({"error": "refresh_token is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            refresh = RefreshToken(refresh_token)
            user_id = refresh['id']  # 토큰 payload에서 id 가져오기
            user = User.objects.get(id=user_id)

            if user.user_role not in ['admin', 'customer', 'owner']:
                return Response({"error": "권한 없음"}, status=status.HTTP_403_FORBIDDEN)


            access_token = str(refresh.access_token)
            return Response({"access_token": access_token}, status=status.HTTP_200_OK)
        except TokenError as e:
            return Response({"error": "Invalid or expired refresh token"}, status=status.HTTP_401_UNAUTHORIZED)
        

# User api 관련 -----------------------------------------------------
# User 전체 조회
class UserList(APIView):
    authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAdminRole]
    @swagger_auto_schema(
        operation_summary = "User 목록 조회",
        operation_description = "모든 User을 조회합니다.",
        responses={200: UserSerializer(many=True)}
    )
    def get(self,request):
        print('asfsd')
        # user_id = request.user.id
        # print(user_id)
        users = User.objects.all()
        #print(users)
        serializer = UserSerializer(users,many=True)
        return Response(serializer.data)