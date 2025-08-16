from django.shortcuts import render

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db.models import Q, Max
from datetime import datetime, timedelta
import math
import requests  # 외부 api 호출용
import random  # 더미 데이터 랜덤 선택용!

from .models import Store, StoreItem, StoreSpace, StoreMenu, StoreMenuSpace
from reservations.models import UserLike

from rest_framework import status

# Swagger 관련 import
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from datetime import datetime


# 거리 계산 함수 (직선거리, haversine)
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # 지구 반지름(단위: m)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return int(R * c)


# 도로명주소 2개 입력받아 각 위도, 경도, 도로 길이(미터) 리턴하는 외부 API 호출 함수 예시
# 실제 API 스펙에 따라 리턴 값 형식과 호출 내용을 수정해야 함!
def get_distance_and_coords_from_two_addresses(addr1: str, addr2: str):
    """
    예시: addr1, addr2 도로명주소를 받아서
    {
        'distance': 총 도로 길이 (m),
        'addr1_lat': 위도,
        'addr1_lng': 경도,
        'addr2_lat': 위도,
        'addr2_lng': 경도
    }
    형태의 dict 반환
    실패 시 None 반환
    """
    # 실제 API 호출 부분 (주석처리했음... 맞춰서 수정하기)
    """
    API_URL = "https://example.externalapi.com/roadlength"
    params = {"address1": addr1, "address2": addr2}
    headers = {"Authorization": "Bearer YOUR_ACCESS_TOKEN"}

    try:
        resp = requests.get(API_URL, headers=headers, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        # data에서 원하는 키 읽어 리턴
        return {
            'distance': data.get('distance'),
            'addr1_lat': data.get('addr1_lat'),
            'addr1_lng': data.get('addr1_lng'),
            'addr2_lat': data.get('addr2_lat'),
            'addr2_lng': data.get('addr2_lng'),
        }
    except Exception as e:
        # 로깅 등 처리 가능
        return None
    """

    # [더미 데이터] - 테스트용: 매 호출마다 랜덤 출력되도록 해둠... 근데 이부분 작동 안 하는듯? 아래에 하드코딩 추가함
    dummy_cases = [
        {
            "distance": 14000,
            "addr1_lat": 37.5665,
            "addr1_lng": 126.9780,  # 서울 시청
            "addr2_lat": 37.4979,
            "addr2_lng": 127.0276,  # 강남역
        },
        {
            "distance": 8000,
            "addr1_lat": 37.5714,
            "addr1_lng": 126.9768,  # 광화문
            "addr2_lat": 37.5133,
            "addr2_lng": 127.1025,  # 잠실
        },
        {
            "distance": 25000,
            "addr1_lat": 37.5219,
            "addr1_lng": 126.9246,  # 여의도
            "addr2_lat": 37.4563,
            "addr2_lng": 126.7052,  # 인천
        },
    ]
    return random.choice(dummy_cases)


class StoreListView(APIView):
    # permission_classes = [AllowAny]  # JWT 인증 추가
    permission_classes = [
        IsAuthenticated
    ]  # JWT 인증(RF SimpleJWT 등 사용 시 윗줄을 주석처리, 이거 활성화)

    @swagger_auto_schema(
        operation_summary="가게 목록 조회",
        operation_description="""
        지정된 시간 슬롯과 (선택적) 카테고리에 맞는 가게 리스트를 반환합니다.
        - time: 0~36 시간 값 (24 이상이면 다음날 계산)
        - store_category: 카테고리 필터링 가능
        """,
        manual_parameters=[
            openapi.Parameter(
                "time",
                openapi.IN_QUERY,
                description="예약 가능 시간 (0~36)",
                type=openapi.TYPE_INTEGER,
                required=True,
            ),
            openapi.Parameter(
                "store_category",
                openapi.IN_QUERY,
                description="가게 카테고리",
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                description="성공 시 가게 목록 반환",
                examples={
                    "application/json": [
                        {
                            "store_id": 1,
                            "store_name": "강남 미용실",
                            "distance": 14000,
                            "on_foot": 200,
                            "store_image_url": "https://example.com/store.jpg",
                            "menu_name": "커트",
                            "menu_id": 10,
                            "max_discount_rate": 30,
                            "max_discount_menu": "커트",
                            "max_discount_price_origin": 20000,
                            "max_discount_price": 14000,
                            "is_liked": True,
                            "liked_id": 55,
                        }
                    ]
                },
            ),
            400: openapi.Response(
                description="잘못된 요청",
                examples={"application/json": {"error": "Invalid time"}},
            ),
        },
    )
    def get(self, request):
        # 필수 파라미터 확인할 것!
        try:
            time_filter = int(request.GET.get("time"))
        except (TypeError, ValueError):
            return Response({"error": "Invalid time"}, status=400)
        if not 0 <= time_filter <= 36:
            return Response({"error": "time은 0~36 사이여야 합니다."}, status=400)

        category = request.GET.get("store_category")

        # JWT 인증 및 예외처리 추가
        user = request.user  # JWT 인증으로 이미 로그인한 사용자 객체가 들어있음
        if not user or not user.is_authenticated:
            return Response(
                {"error": "인증이 필요합니다."}, status=401
            )  # 미인증시 401 반환
        user_address = getattr(user, "user_address", None)
        if not user_address:
            return Response(
                {"error": "사용자 주소 정보가 필요합니다."}, status=400
            )  # 주소 필요시 400 반환

        # user = (
        #     request.user
        #     if getattr(request, "user", None) and request.user.is_authenticated
        #     else None
        # )
        # user_address = None
        # if user:
        #     user_address = getattr(
        #         user, "user_address", None

        today = datetime.now().date()
        target_date = today
        target_time = time_filter
        if time_filter >= 24:
            target_date = today + timedelta(days=1)
            target_time = time_filter - 24

        # 예약 가능한 store item 쿼리
        qs = StoreItem.objects.filter(
            item_reservation_date=target_date,
            item_reservation_time=target_time,
            item_stock__gt=0,
            store__is_active=True,
        )
        if category:
            qs = qs.filter(store__store_category=category)

        # 가게별 최대 할인율 계산
        max_discounts = qs.values("store_id").annotate(
            max_rate=Max("max_discount_rate")
        )

        # 가게별 최대 할인율에 해당하는 StoreItem만 선택
        filtered_items = []
        use_cheaper_on_tie = True  # 같은 할인율이면 더 저렴한 메뉴 선택 여부!
        for md in max_discounts:
            store_id = md["store_id"]
            max_rate = md["max_rate"]
            if use_cheaper_on_tie:
                item = (
                    qs.filter(store_id=store_id, max_discount_rate=max_rate)
                    .select_related("store", "menu")
                    .order_by("menu__menu_price", "item_id")
                    .first()
                )
            else:
                item = (
                    qs.filter(store_id=store_id, max_discount_rate=max_rate)
                    .select_related("store", "menu")
                    .first()
                )
            if item:
                filtered_items.append(item)

        results = []
        for item in filtered_items:
            store = item.store
            store_address = getattr(
                store, "store_address", None
            )  # 실제 필드명에 맞게 수정해야 함

            # 테스트용 더미 주소 자동 세팅
            if not user_address:
                user_address = "서울특별시 중구 세종대로 110"  # 테스트용 사용자 주소 (서울시청 주소임)
            if not store_address:
                store_address = "서울특별시 강남구 강남대로 396"  # 테스트용 매장 주소 (강남역 주소임)

            # 실제 API 호출 사용 시 주석 해제, 더미 데이터 부분은 주석 처리하여 전환 가능
            if user_address and store_address:
                # 실제 API 호출 (주석처리)
                # api_result = get_distance_and_coords_from_two_addresses(user_address, store_address)

                # 더미 데이터 사용
                api_result = get_distance_and_coords_from_two_addresses(
                    user_address, store_address
                )
                if api_result:
                    distance = api_result.get("distance", 0)
                    user_lat = api_result.get("addr1_lat", 0)
                    user_lng = api_result.get("addr1_lng", 0)
                    store_lat = api_result.get("addr2_lat", 0)
                    store_lng = api_result.get("addr2_lng", 0)
                else:
                    distance = 0
                    user_lat = user_lng = store_lat = store_lng = 0
            elif user_address or store_address:  # 한쪽만 주소가 있을 때
                distance = 0
                user_lat = user_lng = store_lat = store_lng = 0
            else:
                distance = 0

            on_foot = distance // 70 if distance else 0  # 대략 70m/분으로 가정

            # is_liked, liked_id = False, 0
            # if user:
            #     like = UserLike.objects.filter(user=user, store=store).first()
            #     if like:
            #         is_liked = True
            #         liked_id = like.like_id

            # 찜 정보 always 페어 반환
            is_liked, liked_id = False, 0
            like = UserLike.objects.filter(user=user, store=store).first()
            if like:
                is_liked = True
                liked_id = like.like_id

            menu = item.menu
            results.append(
                {
                    "store_id": store.store_id,
                    "store_name": store.store_name,
                    "distance": distance,
                    "on_foot": on_foot,
                    "store_image_url": store.store_image_url,
                    "menu_name": menu.menu_name,
                    "menu_id": menu.menu_id,
                    "max_discount_rate": int(item.max_discount_rate * 100),
                    "max_discount_menu": menu.menu_name,
                    "max_discount_price_origin": menu.menu_price,
                    "max_discount_price": int(
                        menu.menu_price * (1 - item.max_discount_rate)
                    ),
                    "is_liked": is_liked,
                    "liked_id": liked_id,
                }
            )

        # 거리 오름차순 정렬 (가까운 순으로 보이게)
        results.sort(key=lambda x: x["distance"])
        return Response(results)


class NumOfSpacesView(APIView):
    # 인증 뺐음...
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_summary="특정 Store의 Space 목록 조회",
        operation_description="store_id에 속한 모든 Space의 개수와 space_id 목록 반환. is_active=False, is_dummy=True도 포함.",
        responses={
            200: openapi.Response(
                description="성공",
                examples={
                    "application/json": {
                        "count": 2,
                        "space_ids": [{"space_id": 101}, {"space_id": 102}],
                    }
                },
            ),
            404: openapi.Response(
                description="존재하지 않는 store_id",
                examples={
                    "application/json": {
                        "errorCode": "STORE_NOT_FOUND",
                        "message": "존재하지 않는 store_id입니다.",
                    }
                },
            ),
        },
    )
    def get(self, request, store_id):
        # Store 존재 여부 확인
        try:
            store = Store.objects.get(pk=store_id)
        except Store.DoesNotExist:
            return Response(
                {
                    "errorCode": "STORE_NOT_FOUND",
                    "message": "존재하지 않는 store_id입니다.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        # 해당 Store의 모든 Space 가져오기
        space_list = list(
            StoreSpace.objects.filter(store=store).values_list("space_id", flat=True)
        )
        return Response(
            {
                "count": len(space_list),
                "space_ids": [{"space_id": sid} for sid in space_list],
            },
            status=status.HTTP_200_OK,
        )


class StoreSpacesDetailView(APIView):
    authentication_classes = []
    permission_classes = [IsAuthenticated]  # 인증 필요

    @swagger_auto_schema(
        operation_summary="특정 Store의 Space 상세 목록 조회",
        operation_description="""
        특정 store_id에 해당하는 가게 기본 정보와 하위 Space 목록을 반환합니다.
        - 쿼리 파라미터 `time`을 반드시 전달해야 합니다 (0~36 시각, int).
        - 각 Space 항목에는 최대 할인율과 해당 시간대 예약 가능 여부를 포함합니다.
        """,
        manual_parameters=[
            openapi.Parameter(
                "time",
                openapi.IN_QUERY,
                description="조회할 시간대 (0~36)",
                type=openapi.TYPE_INTEGER,
                required=True,
            ),
        ],
        responses={
            200: openapi.Response(
                description="성공 응답",
                examples={
                    "application/json": {
                        "store_name": "가게 이름",
                        "store_category": "생활/공간",
                        "store_address": "서울시 강남구 ...",
                        "store_image_url": "https://example.com/image.jpg",
                        "store_description": "1대1 필라테스",
                        "distance": 350,
                        "on_foot": 5,
                        "spaces": [
                            {
                                "space_id": 101,
                                "space_name": "A 강사",
                                "space_image_url": "https://example.com/spaceA.jpg",
                                "max_discount_rate": 20,
                                "is_possible": True,
                            }
                        ],
                    }
                },
            ),
            400: openapi.Response(
                description="잘못된 요청",
                examples={
                    "application/json": {
                        "error": "`time` query parameter는 필수이며 정수여야 합니다."
                    }
                },
            ),
            404: openapi.Response(
                description="Store 없음",
                examples={
                    "application/json": {
                        "errorCode": "STORE_NOT_FOUND",
                        "message": "해당 store_id의 매장이 존재하지 않습니다.",
                    }
                },
            ),
        },
    )
    def get(self, request, store_id):
        # --- 필수 쿼리 파라미터 확인 ---
        try:
            time_filter = int(request.GET.get("time"))
        except (TypeError, ValueError):
            return Response(
                {"error": "`time` query parameter는 필수이며 정수여야 합니다."},
                status=400,
            )

        if not 0 <= time_filter <= 36:
            return Response({"error": "`time`값은 0과 36 사이여야 합니다."}, status=400)

        # --- Store 조회 ---
        try:
            store = Store.objects.get(pk=store_id)
        except Store.DoesNotExist:
            return Response(
                {
                    "errorCode": "STORE_NOT_FOUND",
                    "message": "해당 store_id의 매장이 존재하지 않습니다.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        today = datetime.now().date()
        target_date = today
        target_time = time_filter  # 날짜/시간 보정용 변수들
        if time_filter >= 24:  # 24이상은 다음날로 계산
            target_date = today + timedelta(days=1)
            target_time = time_filter - 24

        # --- Store 기본 정보 ---
        store_data = {
            "store_name": store.store_name,
            "store_category": store.store_category,
            "store_address": store.store_address,
            "store_image_url": store.store_image_url,
            "store_description": store.store_description,
            # 거리/도보 시간은 외부에서 계산해서 주입받는다고 가정
            "distance": request.GET.get("distance", None),
            "on_foot": request.GET.get("on_foot", None),
            "spaces": [],
        }

        # --- Space 목록 생성 ---
        spaces = StoreSpace.objects.filter(store=store)

        for space in spaces:
            # 최대 할인율 계산
            max_discount = StoreItem.objects.filter(
                store=store,
                space=space,
                item_reservation_date=target_date,
                item_reservation_time=target_time,
            ).aggregate(Max("max_discount_rate"))["max_discount_rate__max"]

            max_discount_percent = int(max_discount * 100) if max_discount else 0

            # 예약 가능 여부 판정
            is_possible = StoreItem.objects.filter(
                store=store,
                space=space,
                item_reservation_date=target_date,
                item_reservation_time=target_time,
                item_stock__gt=0,
            ).exists()

            store_data["spaces"].append(
                {
                    "space_id": space.space_id,
                    "space_name": space.space_name,
                    "space_image_url": space.space_image_url,
                    "max_discount_rate": max_discount_percent,
                    "is_possible": is_possible,
                }
            )

        return Response(store_data, status=200)


class StoreSpaceDetailView(APIView):
    authentication_classes = []
    permission_classes = [IsAuthenticated]  # 인증 필요

    @swagger_auto_schema(
        operation_summary="특정 Space의 상세 정보 및 메뉴 정보 조회",
        manual_parameters=[
            openapi.Parameter(
                "time",
                openapi.IN_QUERY,
                description="조회할 예약 시간 (0~36)",
                type=openapi.TYPE_INTEGER,
                required=True,
            )
        ],
        responses={
            200: openapi.Response(
                description="성공",
                examples={
                    "application/json": {
                        "store_name": "가게 이름",
                        "space_name": "Space 이름",
                        "space_description": "Space 소개/설명",
                        "selected_time": "13:00",
                        "is_liked": False,
                        "space_id": 3,
                        "space_image_url": "https://example.com/space_image.jpg",
                        "menus": [
                            {
                                "menu_id": 45,
                                "menu_name": "coffee",
                                "menu_image_url": "https://example.com/menu_coffee.jpg",
                                "menu_price": 4500,
                                "item_id": 101,
                                "discount_rate": 15,
                                "discounted_price": 3825,
                                "is_available": True,
                            },
                            {
                                "menu_id": 46,
                                "menu_name": "tea",
                                "menu_image_url": "https://example.com/menu_tea.jpg",
                                "menu_price": 3000,
                                "item_id": 102,
                                "discount_rate": 20,
                                "discounted_price": 2400,
                                "is_available": True,
                            },
                        ],
                    }
                },
            ),
            400: openapi.Response(
                description="잘못된 요청",
                examples={
                    "application/json": {
                        "error": "`time` query parameter는 필수이며 정수여야 합니다."
                    }
                },
            ),
            404: openapi.Response(
                description="Space 없음 또는 메뉴 없음",
                examples={
                    "application/json": {
                        "errorCode": "SPACE_NOT_FOUND",
                        "message": "공간(space_id)을 찾을 수 없습니다.",
                    }
                },
            ),
        },
    )
    def get(self, request, space_id):
        # time 쿼리 파라미터 확인 및 검증
        time_param = request.GET.get("time")
        try:
            time_int = int(time_param)
        except (TypeError, ValueError):
            return Response(
                {"error": "`time` query parameter는 필수이며 정수여야 합니다."},
                status=400,
            )
        if not 0 <= time_int <= 36:
            return Response({"error": "`time`은 0과 36 사이여야 합니다."}, status=400)

        try:
            space = StoreSpace.objects.get(pk=space_id)
        except StoreSpace.DoesNotExist:
            return Response(
                {
                    "errorCode": "SPACE_NOT_FOUND",
                    "message": "공간(space_id)을 찾을 수 없습니다.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        store = space.store

        today = datetime.now().date()
        target_date = today
        target_time = time_int
        if time_int >= 24:
            target_date = today + timedelta(days=1)
            target_time = time_int - 24
        selected_time_formatted = f"{target_time}:00"

        # StoreMenuSpace에서 해당 space_id에 연결된 menu들
        menu_spaces = StoreMenuSpace.objects.filter(space=space)
        menu_ids = menu_spaces.values_list("menu_id", flat=True).distinct()

        if not menu_ids:
            return Response(
                {
                    "errorCode": "NO_MENU_AVAILABLE",
                    "message": "해당 공간에 등록된 메뉴가 없습니다.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        menus_data = []
        today = datetime.now().date()

        # 각 메뉴별로 해당 시간대에 할인율 높은 순으로 StoreItem 가져오기
        # 여러 개 모두 반환
        for menu_id in menu_ids:
            menu = StoreMenu.objects.filter(pk=menu_id).first()
            if not menu:
                continue

            # 할인율이 높은 순으로 모든 StoreItem 조회 (item_reservation_date = today, item_reservation_time = time_int)
            store_items = StoreItem.objects.filter(
                menu=menu,
                space=space,
                item_reservation_date=target_date,
                item_reservation_time=target_time,
            ).order_by("-max_discount_rate")

            if not store_items.exists():
                # 재고 없거나 예약 불가능한 경우라도 메뉴는 노출, 빈 상태로 is_available False 처리할 수 있음
                menus_data.append(
                    {
                        "menu_id": menu.menu_id,
                        "menu_name": menu.menu_name,
                        "menu_image_url": menu.menu_image_url,
                        "menu_price": menu.menu_price,
                        "item_id": None,
                        "discount_rate": 0,
                        "discounted_price": menu.menu_price,
                        "is_available": False,
                    }
                )
                continue

            # 메뉴별 StoreItem 여러개 모두 처리
            for item in store_items:
                discounted_price = (
                    int(menu.menu_price * (1 - item.max_discount_rate))
                    if item.max_discount_rate
                    else menu.menu_price
                )
                menus_data.append(
                    {
                        "menu_id": menu.menu_id,
                        "menu_name": menu.menu_name,
                        "menu_image_url": menu.menu_image_url,
                        "menu_price": menu.menu_price,
                        "item_id": item.item_id,
                        "discount_rate": (
                            int(item.max_discount_rate * 100)
                            if item.max_discount_rate
                            else 0
                        ),
                        "discounted_price": discounted_price,
                        "is_available": item.item_stock > 0,
                    }
                )

        # 찜 - 사용자 인증 방식 적용
        user = request.user
        if not user or not user.is_authenticated:
            return Response(
                {"error": "인증이 필요합니다."}, status=401
            )  # 인증 필요시 401 반환

        # 찜 정보 페어 반환
        is_liked = False
        liked_id = 0
        like = UserLike.objects.filter(user=user, store=store).first()
        if like:
            is_liked = True
            liked_id = like.like_id

        # 찜
        # user = (
        #     request.user
        #     if getattr(request, "user", None) and request.user.is_authenticated
        #     else None
        # )
        # is_liked = False
        # liked_id = 0
        # if user:
        #     # "찜" 정보 조회: user와 해당 store에 대해 찜이 있으면 True, liked_id 반영
        #     like = UserLike.objects.filter(user=user, store=store).first()
        #     if like:
        #         is_liked = True
        #         liked_id = like.like_id

        response_data = {
            "store_name": store.store_name,
            "space_name": space.space_name,
            "space_description": space.space_description,
            "selected_time": selected_time_formatted,
            "is_liked": is_liked,
            "liked_id": liked_id,
            "space_id": space.space_id,
            "space_image_url": space.space_image_url,
            "menus": menus_data,
        }

        return Response(response_data)


class StoreSingleSpaceDetailView(APIView):
    permission_classes = [IsAuthenticated]  # 인증 필수
    authentication_classes = []

    @swagger_auto_schema(...)
    def get(self, request, store_id):
        try:
            time_filter = int(request.GET.get("time"))
        except (TypeError, ValueError):
            return Response(
                {"error": "`time` query parameter는 필수이며 정수여야 합니다."},
                status=400,
            )
        if not 0 <= time_filter <= 36:
            return Response({"error": "`time`값은 0과 36 사이여야 합니다."}, status=400)

        try:
            store = Store.objects.get(pk=store_id)
        except Store.DoesNotExist:
            return Response(
                {
                    "errorCode": "STORE_NOT_FOUND",
                    "message": "해당 store_id의 매장이 존재하지 않습니다.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        today = datetime.now().date()
        target_date = today
        target_time = time_filter
        if time_filter >= 24:
            target_date = today + timedelta(days=1)
            target_time = time_filter - 24
        selected_time_formatted = f"{target_time}:00"

        space = StoreSpace.objects.filter(store=store).first()
        if not space:
            return Response(
                {"error": "해당 store에 연결된 space가 없습니다."}, status=404
            )

        # 인증된 사용자만 접근이기 때문에 바로 request.user 사용
        user = request.user

        is_liked = False
        like_id = 0
        like = UserLike.objects.filter(user=user, store=store).first()
        if like:
            is_liked = True
            like_id = like.like_id

        menu_spaces = StoreMenuSpace.objects.filter(space=space)
        menu_ids = menu_spaces.values_list("menu_id", flat=True).distinct()
        menus_data = []
        for menu_id in menu_ids:
            menu = StoreMenu.objects.filter(pk=menu_id).first()
            if not menu:
                continue
            item = (
                StoreItem.objects.filter(
                    menu=menu,
                    space=space,
                    item_reservation_date=target_date,
                    item_reservation_time=target_time,
                )
                .order_by("-max_discount_rate")
                .first()
            )
            if item:
                discounted_price = (
                    int(menu.menu_price * (1 - item.max_discount_rate))
                    if item.max_discount_rate
                    else menu.menu_price
                )
                menus_data.append(
                    {
                        "menu_id": menu.menu_id,
                        "menu_name": menu.menu_name,
                        "menu_image_url": menu.menu_image_url,
                        "item_id": item.item_id,
                        "discount_rate": (
                            int(item.max_discount_rate * 100)
                            if item.max_discount_rate
                            else 0
                        ),
                        "discounted_price": discounted_price,
                        "menu_price": menu.menu_price,
                        "is_available": item.item_stock > 0,
                    }
                )
            else:
                menus_data.append(
                    {
                        "menu_id": menu.menu_id,
                        "menu_name": menu.menu_name,
                        "menu_image_url": menu.menu_image_url,
                        "item_id": None,
                        "discount_rate": 0,
                        "discounted_price": menu.menu_price,
                        "menu_price": menu.menu_price,
                        "is_available": False,
                    }
                )

        store_data = {
            "store_name": store.store_name,
            "store_address": store.store_address,
            "store_image_url": store.store_image_url,
            "store_description": store.store_description,
            "selected_time": selected_time_formatted,
            "distance": request.GET.get("distance", None),
            "on_foot": request.GET.get("on_foot", None),
            "is_liked": is_liked,
            "like_id": like_id,
            "menus": menus_data,
        }
        return Response(store_data, status=200)
