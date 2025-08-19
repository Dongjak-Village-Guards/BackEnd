from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.generics import get_object_or_404

from .models import User
from .serializers import GoogleLoginSerializer, AdminLoginSerializer, UserSerializer, OwnerLoginSerializer
from config.authentication import FirebaseIDTokenAuthentication
from .permissions import *

from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.exceptions import TokenError

from config.kakaoapi import *

# 로깅 파일
from logger import get_logger

logger = get_logger("buynow.accounts")

def view_func(request):
    logger.info("배포 서버에서 호출됨")
    try:
        1 / 0
    except Exception as e:
        logger.error(f"에러 발생: {e}")

# ----------------------------
# 로그인 & 토큰 관련 view
# ----------------------------

# Google 로그인
class GoogleLoginAPIView(APIView):
    authentication_classes = [FirebaseIDTokenAuthentication]  # Firebase 토큰만 인증
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Google 로그인",
        operation_description="Firebase id_token으로 로그인/회원가입 후 JWT 토큰 발급",
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
            400: "유효하지 않은 요청"
        }
    )
    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        user = result["user"]
        created = result["created"]
        message = "회원가입 성공" if created else "로그인 성공"

        return Response({
            "message": message,
            "user_email": user.user_email,
            "user_image_url": user.user_image_url,
            "user_role": user.user_role,
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"]
        }, status=status.HTTP_200_OK)

# Admin 로그인
class AdminLoginAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []  # JWT 필요 없음

    @swagger_auto_schema(
        operation_summary="Admin 로그인",
        operation_description="관리자 로그인/회원가입 후 JWT 토큰 발급",
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
            400: "유효하지 않은 요청",
            403: "관리자 권한 없음"
        }
    )
    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        user = result["user"]
        created = result["created"]
        message = "회원가입 성공" if created else "로그인 성공"

        return Response({
            "message": message,
            "user_role": user.user_role,
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"]
        }, status=status.HTTP_200_OK)


# 공급자 로그인 기능
class OwnerLoginAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []  # JWT 필요 없음

    @swagger_auto_schema(
        operation_summary="Owner 로그인",
        operation_description="공급자 로그인 후 JWT 토큰 발급",
        request_body=OwnerLoginSerializer,
        responses={
            200: openapi.Response(
                description="공급자 로그인 성공",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "message": openapi.Schema(type=openapi.TYPE_STRING),
                        "user_email" : openapi.Schema(type=openapi.TYPE_STRING),
                        "user_role": openapi.Schema(type=openapi.TYPE_STRING),
                        "access_token": openapi.Schema(type=openapi.TYPE_STRING),
                        "refresh_token": openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            ),
            400: "유효하지 않은 요청",
        }
    )
    def post(self, request):
        serializer = OwnerLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.validated_data()

        #user = result["user"]
        user_email = result["user_email"]
        user_role = result["user_role"]
        message = "공급자 로그인 성공"

        return Response({
            "message": message,
            "user_email" : user_email,
            "user_role": user_role,
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"]
        }, status=status.HTTP_200_OK)


# refresh로 access 토큰 재발급
class TokenRefreshAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh_token")
        if not refresh_token:
            return Response({"error": "refresh_token is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            refresh = RefreshToken(refresh_token)
            user_id = refresh['user_id']  # 토큰 payload에서 id 가져오기
            user = User.objects.get(id=user_id)

            if user.user_role not in ['admin', 'customer', 'owner']:
                return Response({"error": "권한 없음"}, status=status.HTTP_403_FORBIDDEN)


            access_token = str(refresh.access_token)
            return Response({"access_token": access_token}, status=status.HTTP_200_OK)
        except TokenError as e:
            return Response({"error": "Invalid or expired refresh token"}, status=status.HTTP_401_UNAUTHORIZED)
        

# ----------------------------
# User API
# ----------------------------
class UserList(APIView):
    authentication_classes = [JWTAuthentication]  # JWT 토큰 인증
    permission_classes = [IsAdminRole]  # 관리자만 접근 가능

    @swagger_auto_schema(
        operation_summary="User 목록 조회",
        operation_description="모든 사용자 조회 (관리자 전용)",
        responses={200: UserSerializer(many=True)}
    )
    def get(self, request):
        users = User.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)
    
class UserDetail(APIView):
    permission_classes = [IsAdminRole]
    @swagger_auto_schema(
        operation_summary = "User 단일 조회",
        operation_description = "해당 id의 User을 조회합니다.",
        responses={200: UserSerializer, 400: "user_id Path 파라미터가 필요합니다.", 404: "존재하지 않는 User"}
    )
    def get(self, request, user_id):
        user = get_object_or_404(User, id = user_id)
        serializer = UserSerializer(user)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_summary = "User 단일 삭제",
        operation_description = "해당 id의 User을 삭제합니다.",
        responses={204: "삭제 완료" , 400: "user_id 가 필요합니다.", 404: "존재하지 않는 User"}
    )
    def delete(self, request,user_id):
        user = get_object_or_404(User, id = user_id)
        user.delete()
        return Response(status = status.HTTP_204_NO_CONTENT)
    
class UserMe(APIView):
    permission_classes = [IsUserRole]
    @swagger_auto_schema(
        operation_summary = "User 본인 조회",
        operation_description = "User 본인의 정보를 조회합니다.",
        responses={200: UserSerializer, 401: "인증이 필요합니다."}
    )
    def get(self, request):
        user = request.user  # JWT 인증으로 이미 로그인한 사용자 객체가 들어있음
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)
    
        serializer = UserSerializer(user)
        return Response(serializer.data)
    
    @swagger_auto_schema(
        operation_summary="User 주소 업데이트",
        operation_description="User 본인의 도로명 주소(user_address)를 업데이트합니다.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'user_address': openapi.Schema(type=openapi.TYPE_STRING, description='도로명 주소'),
            },
            required=['user_address'],
        ),
        responses={200: UserSerializer, 400: "주소가 필요합니다.", 401: "인증이 필요합니다."}
    )
    def patch(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)

        user_address = request.data.get("user_address")
        if not user_address:
            return Response({"error": "주소가 필요합니다."}, status=400)

        # User 모델에 필드 업데이트
        user.user_address = user_address
        user.save()

        serializer = UserSerializer(user)
        return Response(serializer.data)
    

