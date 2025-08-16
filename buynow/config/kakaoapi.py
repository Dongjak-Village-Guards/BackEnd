import os,json,math,requests
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured



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


KAKAO_REST_API_KEY = get_secret("KAKAO_REST_API_KEY")

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # 지구 반지름 (km)
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c # km 단위

def estimate_walk_time(distance_km, speed_kmh=4.5):
    return distance_km / speed_kmh * 60  # 분 단위


# kakao api로 도로명 주소 -> 좌표 변환
def get_coordinates(address):
    if not address:
        print ("도로명 주소가 필요합니다.")
        return None
    
    kakao_api_url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {
			"Authorization" : f"KakaoAK {KAKAO_REST_API_KEY}"
	}
    params = {"query" : address}

    try :
        response = requests.get(kakao_api_url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        documents = data.get("documents")

        if not documents:
            print("주소를 찾을 수 없습니다.")
            return None
        
        # 첫번째 결과 가져오기
        first_result = documents[0]
        x = first_result["x"]
        y = first_result["y"]

        return x , y
    except requests.RequestException as e:
        print(f"Kakao API 요청 실패 : {e}")
        return None

# 직선 거리 & 도보 시간 계산
def get_distance_walktime(store_address, user_address):
    ux, uy = get_coordinates(user_address)
    sx , sy = get_coordinates(store_address)

    if not ux or not uy or not sx or not sy:
        return None,None

    # 문자열 -> float
    ux, uy = float(ux), float(uy)
    sx, sy = float(sx), float(sy)

    distance_km = haversine(uy, ux, sy, sx)  # 위도, 경도 순서 주의
    walk_time_min = estimate_walk_time(distance_km)

    return distance_km, walk_time_min