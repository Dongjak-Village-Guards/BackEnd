from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.decorators import permission_classes

from .models import User
from config.authentication import verify_firebase_id_token
import uuid
#import jwt

# Create your views here.

# 로그인 기능 (Firebase 토큰 받아 사용자 생성or로그인)
@api_view(['POST'])
@permission_classes([AllowAny]) 
def google_login(request):
    id_token = request.data.get('id_token')
    if not id_token:
        return Response({"error" : "ID token is required"}, status = 400)
    role = request.data.get('user_role')
    if not role:
        return Response({"error" : "user role is required"}, status = 400)

    try:
        email = verify_firebase_id_token(id_token) # config/authentication.py 에서의 함수 사용해 토큰에서 email 추출
        user, created = User.objects.get_or_create(user_email = email, defaults= {'user_role' : role})

        return Response({
            'message' : 'Login successful',
            'user_email' : user.user_email,
        })
    except Exception as e:
        return Response({'error': str(e)}, status = 400)