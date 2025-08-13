from django.shortcuts import render
from rest_framework.decorators import api_view,permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import User

import uuid
#import jwt

from .serializers import GoogleLoginSerializer, AdminLoginSerializer

# Create your views here.

# 구글 로그인 기능 (Firebase 토큰 받아 사용자 생성or로그인)
class GoogleLoginAPIView(APIView):
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