# from rest_framework.authentication import BaseAuthentication
# from rest_framework.exceptions import AuthenticationFailed
# from django.contrib.auth import get_user_model
# import firebase_admin
# from firebase_admin import credentials, auth
# from rest_framework.exceptions import AuthenticationFailed
# #import jwt
# import requests

# # 프론트에서 보낸 토큰이 옳은 토큰인 지 검증
# User = get_user_model()
# cred = credentials.Certificate("dongjak-village-guards-3cc0caa945e7.json")
# firebase_admin.initialize_app(cred)

# # 프론트에서 받은 토큰으로 email 가져오는 함수
# def verify_firebase_id_token(id_token):
#     try:
#         decoded_token = auth.verify_id_token(id_token)
#     except Exception as e:
#         raise AuthenticationFailed(f'Invalid Firebase ID token: {str(e)}')

#     email = decoded_token.get('email')
#     if not email:
#         raise AuthenticationFailed('Email not found in token')

#     image_url = decoded_token.get('picture')
#     if not image_url:
#         raise AuthenticationFailed('Image Url not found in token')

#     return email, image_url

# # 프론트에서 전달된 Firebase id_token을 검증하고 user 객체를 반환하는 인증 클래스
# class FirebaseIDTokenAuthentication(BaseAuthentication):

#     def authenticate(self,request):
#         auth_header = request.headers.get('Authorization')
#         if not auth_header or not auth_header.startswith('Bearer '):
#             return None

#         id_token = auth_header.split(' ')[1]

#         try:
#             email, image_url = verify_firebase_id_token(id_token)
#         except AuthenticationFailed as e:
#             raise AuthenticationFailed(f"Invalid Firebase ID token: {str(e)}")

#         user, _ = User.objects.get_or_create(user_email=email, defaults={'user_image_url' : image_url}) # User 테이블에서 email 조건에 맞는 레코드를 가져옴 -> 없으면 새로 생성&저장
#         return (user, None)  # authenticate 함수는 (user, auth) 튜플 반환해야 함

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import get_user_model
import firebase_admin
from firebase_admin import credentials, auth

# import jwt
import requests
import os  # ✅ 경로 처리를 위해 추가

# ==== Firebase 서비스 계정 키 경로 설정 ====
# 1순위: 환경변수에서 읽기 (Mac, Linux, Windows 전부 지원)
#   - Mac/Linux: export FIREBASE_CREDENTIALS_PATH=/경로/파일명.json
#   - Windows(cmd): set FIREBASE_CREDENTIALS_PATH=C:\경로\파일명.json
#   - Windows(PowerShell): $Env:FIREBASE_CREDENTIALS_PATH="C:\경로\파일명.json"
# 2순위: 프로젝트 루트(BASE_DIR)에 있는 파일 사용
BASE_DIR = os.path.dirname(os.path.abspath(os.path.join(__file__, "..", "..")))
default_json_path = os.path.join(
    BASE_DIR, "buynow", "dongjak-village-guards-3cc0caa945e7.json"
)

FIREBASE_CRED_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", default_json_path)

if not os.path.exists(FIREBASE_CRED_PATH):
    raise FileNotFoundError(
        f"Firebase credentials file not found: {FIREBASE_CRED_PATH}"
    )

# 프론트에서 보낸 토큰이 옳은 토큰인지 검증
User = get_user_model()
cred = credentials.Certificate(FIREBASE_CRED_PATH)
firebase_admin.initialize_app(cred)


# 프론트에서 받은 토큰으로 email 가져오는 함수
def verify_firebase_id_token(id_token):
    try:
        decoded_token = auth.verify_id_token(id_token)
    except Exception as e:
        raise AuthenticationFailed(f"Invalid Firebase ID token: {str(e)}")

    email = decoded_token.get("email")
    if not email:
        raise AuthenticationFailed("Email not found in token")

    image_url = decoded_token.get("picture")
    if not image_url:
        raise AuthenticationFailed("Image Url not found in token")

    return email, image_url


# 프론트에서 전달된 Firebase id_token을 검증하고 user 객체를 반환하는 인증 클래스
class FirebaseIDTokenAuthentication(BaseAuthentication):

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        id_token = auth_header.split(" ")[1]

        try:
            email, image_url = verify_firebase_id_token(id_token)
        except AuthenticationFailed:
            raise
        except Exception as e:
            raise AuthenticationFailed(str(e))

        user, _ = User.objects.get_or_create(
            user_email=email, defaults={"user_image_url": image_url}
        )  # User 테이블에서 email 조건에 맞는 레코드를 가져옴 -> 없으면 새로 생성&저장
        return (user, None)  # authenticate 함수는 (user, auth) 튜플 반환해야 함
