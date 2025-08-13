# import subprocess
# import sys
# from sshtunnel import SSHTunnelForwarder
# import os, json

# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# SECRET_FILE = os.path.join(BASE_DIR, "secrets.json")

# with open(SECRET_FILE) as f:
#     secrets = json.load(f)

# def get_secret(key):
#     try:
#         return secrets[key]
#     except KeyError:
#         raise Exception(f"'{key}' 키 에러")

# # EC2 SSH 정보
# EC2_HOST = get_secret("EC2_HOST")
# EC2_USER = get_secret("EC2_USER")
# EC2_KEY_PATH = get_secret("EC2_KEY_PATH")

# # RDS 정보
# ENVIRONMENT = os.getenv('DJANGO_ENV', 'development')  # 환경변수 이용

# RDS_HOSTS = get_secret("RDS_HOSTS")
# RDS_HOST = RDS_HOSTS.get(ENVIRONMENT)
# RDS_PORT = 3306
# LOCAL_PORT = 3307

# if __name__ == "__main__":
#     # 터널 열기
#     with SSHTunnelForwarder(
#         (EC2_HOST, 22),
#         ssh_username=EC2_USER,
#         ssh_pkey=EC2_KEY_PATH,
#         remote_bind_address=(RDS_HOST, RDS_PORT),
#         local_bind_address=('127.0.0.1', LOCAL_PORT),
#     ) as tunnel:
#         print(f"SSH 터널: localhost:{LOCAL_PORT} → {RDS_HOST}:{RDS_PORT}")

#         # Django 명령어 실행
#         try:
#             subprocess.run([sys.executable, "manage.py"] + sys.argv[1:], check=True)
#         except subprocess.CalledProcessError as e:
#             print("명령어 에러", e)

import subprocess
import sys
from sshtunnel import SSHTunnelForwarder
import os
import json
import platform

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRET_FILE = os.path.join(BASE_DIR, "secrets.json")

# secrets.json 존재여부 확인
if not os.path.exists(SECRET_FILE):
    raise FileNotFoundError(f"[오류] secrets.json 파일이 없습니다: {SECRET_FILE}")

# secrets.json 읽기
with open(SECRET_FILE, 'r', encoding='utf-8') as f:
    secrets = json.load(f)

# key 가져오는 함수
def get_secret(key):
    try:
        return secrets[key]
    except KeyError:
        raise Exception(f"[오류] secrets.json에 '{key}' 키가 없습니다.")

# EC2 SSH 정보
EC2_HOST = get_secret("EC2_HOST")
EC2_USER = get_secret("EC2_USER")
# 여러 환경에 대응해서 로컬/서버 자동 경로 전환
EC2_KEY_PATHS = get_secret("EC2_KEY_PATHS")  # secrets.json에서 dict 형태로 받음

# 현재 OS 확인 (Windows, Linux, Darwin(Mac))
current_os = platform.system()

if current_os == "Darwin":  # Mac 로컬 환경
    EC2_KEY_PATH = EC2_KEY_PATHS.get("local")
elif current_os == "Linux":  # Ubuntu 서버 환경 (리눅스 계열)
    EC2_KEY_PATH = EC2_KEY_PATHS.get("server")
else:
    # 그 외 환경이면 local 경로 기본 사용
    EC2_KEY_PATH = EC2_KEY_PATHS.get("local")

# 키 경로 유효성 검사
if not EC2_KEY_PATH or not os.path.exists(EC2_KEY_PATH):
    raise FileNotFoundError(f"[오류] SSH 개인키(.pem) 파일이 없습니다:\n현재 OS: {current_os}\n설정된 경로: {EC2_KEY_PATH}")

# RDS 정보
ENVIRONMENT = os.getenv("DJANGO_ENV", "development")  # 기본 development
RDS_HOSTS = get_secret("RDS_HOSTS")
RDS_HOST = RDS_HOSTS.get(ENVIRONMENT)
if not RDS_HOST:
    raise ValueError(f"[오류] '{ENVIRONMENT}' 환경에 맞는 RDS 주소가 없습니다.")

RDS_PORT = 3306
LOCAL_PORT = 3307

if __name__ == "__main__":
    # SSH 터널 연결
    with SSHTunnelForwarder(
        (EC2_HOST, 22),
        ssh_username=EC2_USER,
        ssh_pkey=EC2_KEY_PATH,
        remote_bind_address=(RDS_HOST, RDS_PORT),
        local_bind_address=("127.0.0.1", LOCAL_PORT),
    ) as tunnel:
        print(f"[성공] SSH 터널 연결: localhost:{LOCAL_PORT} → {RDS_HOST}:{RDS_PORT}")

        # Django 명령 실행
        try:
            subprocess.run([sys.executable, "manage.py"] + sys.argv[1:], check=True)
        except subprocess.CalledProcessError as e:
            print("[오류] Django 명령어 실행 중 문제 발생:", e)
