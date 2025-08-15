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
import time
from sshtunnel import SSHTunnelForwarder
import os
import json
import platform

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRET_FILE = os.path.join(BASE_DIR, "secrets.json")

# secrets.json 존재 여부 확인
if not os.path.exists(SECRET_FILE):
    raise FileNotFoundError(f"[오류] secrets.json 파일이 없습니다: {SECRET_FILE}")

# secrets.json 읽기
with open(SECRET_FILE, "r", encoding="utf-8") as f:
    secrets = json.load(f)


# secrets.json에서 값 가져오기
def get_secret(key):
    try:
        return secrets[key]
    except KeyError:
        raise Exception(f"[오류] secrets.json에 '{key}' 키가 없습니다.")


EC2_HOST = get_secret("EC2_HOST")
EC2_USER = get_secret("EC2_USER")
EC2_KEY_PATHS = get_secret("EC2_KEY_PATHS")  # local/server 경로 둘 다 포함

# 현재 OS에 따라 경로 선택
if platform.system() == "Linux":
    # 서버(Ubuntu)
    EC2_KEY_PATH = EC2_KEY_PATHS.get("server")
else:
    # 로컬(Mac/Windows 모두 포함)
    EC2_KEY_PATH = EC2_KEY_PATHS.get("local")

# ~ 경로를 절대경로로 변환
EC2_KEY_PATH = os.path.expanduser(EC2_KEY_PATH)

# 키파일 존재 여부 확인
if not os.path.exists(EC2_KEY_PATH):
    raise FileNotFoundError(f"[오류] SSH 키 파일이 없습니다: {EC2_KEY_PATH}")

ENVIRONMENT = os.getenv("DJANGO_ENV", "development")
RDS_HOSTS = get_secret("RDS_HOSTS")
RDS_HOST = RDS_HOSTS.get(ENVIRONMENT)

if not RDS_HOST:
    raise ValueError(f"[오류] '{ENVIRONMENT}' 환경에 맞는 RDS 주소가 없습니다.")

RDS_PORT = 3306
LOCAL_PORT = 3307

if __name__ == "__main__":
    with SSHTunnelForwarder(
        (EC2_HOST, 22),
        ssh_username=EC2_USER,
        ssh_pkey=EC2_KEY_PATH,
        remote_bind_address=(RDS_HOST, RDS_PORT),
        local_bind_address=("127.0.0.1", LOCAL_PORT),
    ) as tunnel:
        print(f"[성공] SSH 터널 연결: localhost:{LOCAL_PORT} → {RDS_HOST}:{RDS_PORT}")
        try:
            while True:
                time.sleep(60)  # 60초마다 터널 유지
        except KeyboardInterrupt:
            print("SSH 터널 종료")
