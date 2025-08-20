from config.kakaoapi import get_distance_walktime, get_coordinates

from django.shortcuts import render

from accounts.permissions import IsUserRole, IsAdminRole, IsOwnerRole
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db.models import Q, Max, Count, F, ExpressionWrapper, FloatField
from datetime import datetime, timedelta,date
import math
import requests  # 외부 api 호출용
import random  # 더미 데이터 랜덤 선택용!

from .models import Store, StoreItem, StoreSpace, StoreMenu, StoreMenuSpace, StoreSlot
from reservations.models import UserLike, Reservation
from config.kakaoapi import change_to_cau

from rest_framework import status
from rest_framework.generics import get_object_or_404

# Swagger 관련 import
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from datetime import datetime

from django.contrib.auth import get_user_model  # 사용자 모델 가져오기 <- 최신화!

# 로깅 파일
from logger import get_logger

logger = get_logger("buynow.stores")


def view_func(request):
    logger.info("배포 서버에서 호출됨")
    try:
        1 / 0
    except Exception as e:
        logger.error(f"에러 발생: {e}")


from django.contrib.auth import get_user_model  # 사용자 모델 가져오기 <- 최신화!


class StoreListView(APIView):
    permission_classes = [IsUserRole]  # 인증 필요, admin/customer만 접근 가능

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
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "store_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "store_name": openapi.Schema(type=openapi.TYPE_STRING),
                            "distance": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "on_foot": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "store_image_url": openapi.Schema(type=openapi.TYPE_STRING),
                            "menu_name": openapi.Schema(type=openapi.TYPE_STRING),
                            "menu_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "max_discount_rate": openapi.Schema(
                                type=openapi.TYPE_INTEGER
                            ),
                            "max_discount_menu": openapi.Schema(
                                type=openapi.TYPE_STRING
                            ),
                            "max_discount_price_origin": openapi.Schema(
                                type=openapi.TYPE_INTEGER
                            ),
                            "max_discount_price": openapi.Schema(
                                type=openapi.TYPE_INTEGER
                            ),
                            "is_liked": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            "liked_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        },
                    ),
                ),
            ),
            400: openapi.Response(
                description="잘못된 요청",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "error": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
        },
    )
    def get(self, request):
        user = request.user  # JWT 인증으로 이미 로그인한 사용자 객체가 들어있음
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)
        User = get_user_model()
        fresh_user = User.objects.get(pk=user.id)  # DB에서 항상 최신 데이터
        user_address = fresh_user.user_address

        # 필수 파라미터 확인할 것!
        try:
            time_filter = int(request.GET.get("time"))
        except (TypeError, ValueError):
            return Response({"error": "Invalid time"}, status=400)
        if not 0 <= time_filter <= 36:
            return Response({"error": "time은 0~36 사이여야 합니다."}, status=400)

        if not user_address:
            return Response(
                {"error": "사용자 주소 정보가 필요합니다."}, status=400
            )  # 주소 필요시 400 반환

        category = request.GET.get("store_category", None)
        today = datetime.now().date()
        target_date = today
        target_time = time_filter
        if time_filter >= 24:
            target_date = today + timedelta(days=1)
            target_time = time_filter - 24

        # 기존 필터 조건에서 item_stock__gt=0 제거 —> 재고 0인 아이템 확인해야 하므로 따로 처리
        base_filters = {
            "item_reservation_date": target_date,
            "item_reservation_time": target_time,
            "store__is_active": True,
        }

        if category:
            normalized_category = category.strip().strip('"')
            if normalized_category != "":
                base_filters["store__store_category__iexact"] = normalized_category

        # 1. 모든 StoreItem 조회 (재고 0 포함)
        all_items_qs = StoreItem.objects.filter(**base_filters).select_related(
            "store", "menu", "space"
        )

        # 2. space별로 재고 0인 item 존재 여부 집계 -> 비활성 Space 판단
        space_stock_zeros = (
            all_items_qs.values("space_id", "store_id")
            .annotate(zero_stock_count=Count("item_id", filter=Q(item_stock=0)))
            .filter(zero_stock_count__gt=0)
        )

        # 비활성화된 space id 집합
        inactive_space_ids = set(space["space_id"] for space in space_stock_zeros)

        # 3. 활성화된 StoreItem만 필터링 (해당 시간대 + 재고 > 0 + space_id not in 비활성 space)
        active_items_qs = all_items_qs.filter(item_stock__gt=0).exclude(
            space_id__in=inactive_space_ids
        )

        # 4. 활성화된 space가 한 개라도 있는 store_id 집합
        active_store_ids = active_items_qs.values_list("store_id", flat=True).distinct()

        # 5. 그 store_id에 해당하는 StoreItem만 필터링
        filtered_items_qs = active_items_qs.filter(store_id__in=active_store_ids)

        # 6. store별 최대 할인율 계산 (할인율 큰 순 정렬을 위해 max_discount_rate, 할인금액 계산 필드 추가)
        # 할인 금액 컬럼(ExpressionWrapper) 추가
        discount_amount_expr = ExpressionWrapper(
            F("menu__menu_price") * F("max_discount_rate"), output_field=FloatField()
        )

        max_discount_items = (
            filtered_items_qs.annotate(discount_amount=discount_amount_expr)
            .values("store_id")
            .annotate(
                max_discount_rate=Max("max_discount_rate"),
                max_discount_amount=Max("discount_amount"),
            )
        )

        # 7. 최대 할인 금액 기준 오름차순 정렬 후 각 store별 최대 할인율 아이템 선택
        results = []
        use_cheaper_on_tie = True  # 할인액이 같으면 더 저렴한 메뉴 선택 판단

        for discount_data in max_discount_items:
            store_id = discount_data["store_id"]
            max_rate = discount_data["max_discount_rate"]
            max_amount = discount_data["max_discount_amount"]

            # 할인율, 할인액 기준 필터
            candidate_items = filtered_items_qs.filter(
                store_id=store_id,
                max_discount_rate=max_rate,
            ).annotate(discount_amount=discount_amount_expr)

            if use_cheaper_on_tie:
                item = (
                    candidate_items.order_by(
                        "-discount_amount",  # 할인액 큰 순
                        "menu__menu_price",  # 메뉴 가격 낮은 순
                        "item_id",
                    )
                    .select_related("store", "menu")
                    .first()
                )
            else:
                item = (
                    candidate_items.order_by("-discount_amount", "item_id")
                    .select_related("store", "menu")
                    .first()
                )

            if not item:
                continue

            store = item.store
            store_address = getattr(store, "store_address", None)

            # 거리, 도보 계산 (기존 로직 유지)
            if user_address and store_address:
                distance_km, walk_time_min = get_distance_walktime(
                    store_address, user_address
                )
                distance = int(distance_km * 1000) if distance_km is not None else 0
                on_foot = int(walk_time_min) if walk_time_min is not None else 0
            else:
                distance = 0
                on_foot = 0

            # 찜 정보 조회 (기존 로직 유지)
            is_liked, liked_id = False, 0
            like = UserLike.objects.filter(user=user, store=store).first()
            if like:
                is_liked = True
                liked_id = like.like_id

            results.append(
                {
                    "store_id": store_id,
                    "store_name": store.store_name,
                    "distance": distance,
                    "on_foot": on_foot,
                    "store_image_url": store.store_image_url,
                    "menu_name": item.menu.menu_name,
                    "menu_id": item.menu.menu_id,
                    "max_discount_rate": int(item.max_discount_rate * 100),
                    "max_discount_menu": item.menu.menu_name,
                    "max_discount_price_origin": item.menu.menu_price,
                    "max_discount_price": int(
                        item.menu.menu_price * (1 - item.max_discount_rate)
                    ),
                    "is_liked": is_liked,
                    "liked_id": liked_id,
                }
            )

        # 거리 오름차순 정렬
        results.sort(key=lambda x: x["distance"])
        return Response(results)


class NumOfSpacesView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]  # 인증 필요 없음

    @swagger_auto_schema(
        operation_summary="특정 Store의 Space 개수 및 ID 목록 조회",
        operation_description="store_id에 속한 모든 Space의 개수와 space_id 목록 반환. is_active=False, is_dummy=True도 포함.",
        responses={
            200: openapi.Response(
                description="성공",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "count": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "space_ids": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "space_id": openapi.Schema(
                                        type=openapi.TYPE_INTEGER
                                    ),
                                },
                            ),
                        ),
                    },
                ),
            ),
            404: openapi.Response(
                description="존재하지 않는 store_id",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "errorCode": openapi.Schema(type=openapi.TYPE_STRING),
                        "message": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
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
    permission_classes = [IsUserRole]  # 인증 필요

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
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "store_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "store_category": openapi.Schema(type=openapi.TYPE_STRING),
                        "store_address": openapi.Schema(type=openapi.TYPE_STRING),
                        "store_image_url": openapi.Schema(type=openapi.TYPE_STRING),
                        "store_description": openapi.Schema(type=openapi.TYPE_STRING),
                        "distance": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "on_foot": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "spaces": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "space_id": openapi.Schema(
                                        type=openapi.TYPE_INTEGER
                                    ),
                                    "space_name": openapi.Schema(
                                        type=openapi.TYPE_STRING
                                    ),
                                    "space_image_url": openapi.Schema(
                                        type=openapi.TYPE_STRING
                                    ),
                                    "max_discount_rate": openapi.Schema(
                                        type=openapi.TYPE_INTEGER
                                    ),
                                    "is_possible": openapi.Schema(
                                        type=openapi.TYPE_BOOLEAN
                                    ),
                                },
                            ),
                        ),
                    },
                ),
            ),
            400: openapi.Response(
                description="잘못된 요청",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "error": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
            404: openapi.Response(
                description="Store 없음",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "errorCode": openapi.Schema(type=openapi.TYPE_STRING),
                        "message": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
        },
    )
    def get(self, request, store_id):
        user = request.user
        if not request.user or not request.user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)
        User = get_user_model()
        fresh_user = User.objects.get(pk=user.id)  # DB에서 항상 최신 데이터
        user_address = fresh_user.user_address

        # 필수 쿼리 파라미터 확인
        try:
            time_filter = int(request.GET.get("time"))
        except (TypeError, ValueError):
            return Response(
                {"error": "`time` query parameter는 필수이며 정수여야 합니다."},
                status=400,
            )

        if not 0 <= time_filter <= 36:
            return Response({"error": "`time`값은 0과 36 사이여야 합니다."}, status=400)

        # Store 조회
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

        # user_address = getattr(request.user, "user_address", None)
        store_address = getattr(store, "store_address", None)

        if user_address and store_address:
            distance_km, walk_time_min = get_distance_walktime(
                store_address, user_address
            )
            distance = int(distance_km * 1000) if distance_km is not None else 0
            on_foot = int(walk_time_min) if walk_time_min is not None else 0
        else:
            distance = 0
            on_foot = 0

        store_data = {
            "store_name": store.store_name,
            "store_category": store.store_category,
            "store_address": store.store_address,
            "store_image_url": store.store_image_url,
            "store_description": store.store_description,
            "distance": distance,
            "on_foot": on_foot,
            "spaces": [],
        }

        # Space 목록 생성
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
            # 재고가 0인 아이템이 하나라도 있는지 체크
            has_zero_stock = StoreItem.objects.filter(
                store=store,
                space=space,
                item_reservation_date=target_date,
                item_reservation_time=target_time,
                item_stock=0,
            ).exists()

            if has_zero_stock:
                is_possible = False
            else:
                # 재고 1 이상인 아이템 존재 여부
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
    permission_classes = [IsUserRole]  # 인증 필요, admin/customer만 접근 가능

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
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "store_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "space_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "space_description": openapi.Schema(type=openapi.TYPE_STRING),
                        "selected_time": openapi.Schema(type=openapi.TYPE_STRING),
                        "is_liked": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        "liked_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "space_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "space_image_url": openapi.Schema(type=openapi.TYPE_STRING),
                        "menus": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "menu_id": openapi.Schema(
                                        type=openapi.TYPE_INTEGER
                                    ),
                                    "menu_name": openapi.Schema(
                                        type=openapi.TYPE_STRING
                                    ),
                                    "menu_image_url": openapi.Schema(
                                        type=openapi.TYPE_STRING
                                    ),
                                    "menu_price": openapi.Schema(
                                        type=openapi.TYPE_INTEGER
                                    ),
                                    "item_id": openapi.Schema(
                                        type=openapi.TYPE_INTEGER, nullable=True
                                    ),
                                    "discount_rate": openapi.Schema(
                                        type=openapi.TYPE_INTEGER
                                    ),
                                    "discounted_price": openapi.Schema(
                                        type=openapi.TYPE_INTEGER
                                    ),
                                    "is_available": openapi.Schema(
                                        type=openapi.TYPE_BOOLEAN
                                    ),
                                },
                            ),
                        ),
                    },
                ),
            ),
            400: openapi.Response(
                description="잘못된 요청",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "error": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
            404: openapi.Response(
                description="Space 없음 또는 메뉴 없음",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "errorCode": openapi.Schema(type=openapi.TYPE_STRING),
                        "message": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
        },
    )
    def get(self, request, space_id):
        user = request.user
        if not request.user or not request.user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)
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
    permission_classes = [IsUserRole]  # 인증 필요, admin/customer만 접근 가능

    @swagger_auto_schema(
        operation_summary="특정 Store 단일 Space 상세 조회",
        manual_parameters=[
            openapi.Parameter(
                "time",
                openapi.IN_QUERY,
                description="조회할 시간대 (0~36)",
                type=openapi.TYPE_INTEGER,
                required=True,
            ),
        ],
        responses={  # 필요한 응답 구조 schema로 선언
            200: openapi.Response(
                description="성공 응답",
                schema=openapi.Schema(  # Store 상세와 menu 필드들만 필요에 따라 타입 명시
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "store_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "store_address": openapi.Schema(type=openapi.TYPE_STRING),
                        "store_image_url": openapi.Schema(type=openapi.TYPE_STRING),
                        "store_description": openapi.Schema(type=openapi.TYPE_STRING),
                        "selected_time": openapi.Schema(type=openapi.TYPE_STRING),
                        "distance": openapi.Schema(
                            type=openapi.TYPE_INTEGER, nullable=True
                        ),
                        "on_foot": openapi.Schema(
                            type=openapi.TYPE_INTEGER, nullable=True
                        ),
                        "is_liked": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        "like_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "menus": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "menu_id": openapi.Schema(
                                        type=openapi.TYPE_INTEGER
                                    ),
                                    "menu_name": openapi.Schema(
                                        type=openapi.TYPE_STRING
                                    ),
                                    "menu_image_url": openapi.Schema(
                                        type=openapi.TYPE_STRING
                                    ),
                                    "item_id": openapi.Schema(
                                        type=openapi.TYPE_INTEGER, nullable=True
                                    ),
                                    "discount_rate": openapi.Schema(
                                        type=openapi.TYPE_INTEGER
                                    ),
                                    "discounted_price": openapi.Schema(
                                        type=openapi.TYPE_INTEGER
                                    ),
                                    "menu_price": openapi.Schema(
                                        type=openapi.TYPE_INTEGER
                                    ),
                                    "is_available": openapi.Schema(
                                        type=openapi.TYPE_BOOLEAN
                                    ),
                                },
                            ),
                        ),
                    },
                ),
            ),
            400: openapi.Response(
                description="잘못된 요청",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "error": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
            404: openapi.Response(
                description="Store/Space 없음",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "errorCode": openapi.Schema(type=openapi.TYPE_STRING),
                        "message": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
        },
    )
    def get(self, request, store_id):
        user = request.user
        if not request.user or not request.user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)
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
        User = get_user_model()
        fresh_user = User.objects.get(pk=user.id)  # DB에서 항상 최신 데이터
        user_address = fresh_user.user_address

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

        # user_address = getattr(request.user, "user_address", None)
        store_address = getattr(store, "store_address", None)

        if user_address and store_address:
            distance_km, walk_time_min = get_distance_walktime(
                store_address, user_address
            )
            distance = int(distance_km * 1000) if distance_km is not None else 0
            on_foot = int(walk_time_min) if walk_time_min is not None else 0
        else:
            distance = 0
            on_foot = 0

        store_data = {
            "store_name": store.store_name,
            "store_address": store.store_address,
            "store_image_url": store.store_image_url,
            "store_description": store.store_description,
            "selected_time": selected_time_formatted,
            "distance": distance,
            "on_foot": on_foot,
            "is_liked": is_liked,
            "like_id": like_id,
            "menus": menus_data,
        }
        return Response(store_data, status=200)


class StoreItemDetailView(APIView):
    permission_classes = [IsUserRole]

    @swagger_auto_schema(
        operation_summary="특정 Menu 단일 조회 (예약화면용)",
        operation_description="특정 item_id에 대한 메뉴 및 매장, 예약 가능한 시간 등 상세 정보를 반환합니다.",
        manual_parameters=[
            openapi.Parameter(
                "item_id",
                openapi.IN_PATH,
                description="예약하려는 건의 아이템 id",
                type=openapi.TYPE_INTEGER,
                required=True,
                example=1001,
            )
        ],
        responses={
            200: openapi.Response(
                description="성공",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "store_name": openapi.Schema(
                            type=openapi.TYPE_STRING, description="매장 이름"
                        ),
                        "store_address": openapi.Schema(
                            type=openapi.TYPE_STRING, description="매장 주소"
                        ),
                        "store_image_url": openapi.Schema(
                            type=openapi.TYPE_STRING, description="매장 대표 이미지"
                        ),
                        "store_description": openapi.Schema(
                            type=openapi.TYPE_STRING, description="매장 설명"
                        ),
                        "selected_time": openapi.Schema(
                            type=openapi.TYPE_STRING, description="선택 시간 (HH:MM)"
                        ),
                        "distance": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description="거리 (미터)",
                            nullable=True,
                        ),
                        "on_foot": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description="도보 시간 (분)",
                            nullable=True,
                        ),
                        "is_liked": openapi.Schema(
                            type=openapi.TYPE_BOOLEAN, description="찜 여부"
                        ),
                        "liked_id": openapi.Schema(
                            type=openapi.TYPE_INTEGER, description="찜 아이디"
                        ),
                        "menu_id": openapi.Schema(
                            type=openapi.TYPE_INTEGER, description="메뉴 고유 ID"
                        ),
                        "menu_name": openapi.Schema(
                            type=openapi.TYPE_STRING, description="메뉴 이름"
                        ),
                        "menu_image_url": openapi.Schema(
                            type=openapi.TYPE_STRING, description="메뉴 대표 이미지"
                        ),
                        "item_id": openapi.Schema(
                            type=openapi.TYPE_INTEGER, description="아이템 고유 ID"
                        ),
                        "discount_rate": openapi.Schema(
                            type=openapi.TYPE_INTEGER, description="할인율(%)"
                        ),
                        "discounted_price": openapi.Schema(
                            type=openapi.TYPE_INTEGER, description="할인 적용된 가격"
                        ),
                        "menu_price": openapi.Schema(
                            type=openapi.TYPE_INTEGER, description="메뉴 정가"
                        ),
                    },
                ),
            ),
            400: openapi.Response(
                description="잘못된 요청",
                examples={
                    "application/json": {
                        "errorCode": "BAD_REQUEST",
                        "message": "사용자 주소 또는 매장 주소가 없습니다.",
                    }
                },
            ),
            401: openapi.Response(
                description="인증 필요",
                examples={
                    "application/json": {
                        "errorCode": "UNAUTHORIZED",
                        "message": "인증이 필요합니다.",
                    }
                },
            ),
            404: openapi.Response(
                description="아이템 없음",
                examples={
                    "application/json": {
                        "errorCode": "ITEM_NOT_FOUND",
                        "message": "해당 item_id에 해당하는 아이템이 없습니다.",
                    }
                },
            ),
        },
    )
    def get(self, request, item_id):
        user = request.user
        if not user or not user.is_authenticated:
            return Response(
                {"errorCode": "UNAUTHORIZED", "message": "인증이 필요합니다."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        User = get_user_model()
        fresh_user = User.objects.get(pk=user.id)  # DB에서 항상 최신 데이터
        user_address = fresh_user.user_address

        try:
            item = StoreItem.objects.select_related("store", "menu").get(
                item_id=item_id
            )
        except StoreItem.DoesNotExist:
            return Response(
                {
                    "errorCode": "ITEM_NOT_FOUND",
                    "message": "해당 item_id에 해당하는 아이템이 없습니다.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        store = item.store
        menu = item.menu
        # user_address = getattr(user, "user_address", None)
        store_address = getattr(store, "store_address", None)

        if not user_address or not store_address:
            return Response(
                {
                    "errorCode": "BAD_REQUEST",
                    "message": "사용자 주소 또는 매장 주소가 없습니다.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 거리, 도보 시간 계산 (km, 분 단위)
        distance_km, walk_time_min = get_distance_walktime(store_address, user_address)

        # 거리 미터 단위, 도보시간 분 단위, 없으면 null 처리
        if distance_km is not None:
            distance = int(distance_km * 1000)
        else:
            distance = None

        if walk_time_min is not None:
            on_foot = int(round(walk_time_min))
        else:
            on_foot = None

        # 찜 정보 조회
        is_liked = False
        liked_id = 0
        like = UserLike.objects.filter(user=user, store=store).first()
        if like:
            is_liked = True
            liked_id = like.like_id

        selected_time = f"{item.item_reservation_time}:00"

        discount_rate_percent = (
            int(item.max_discount_rate * 100) if item.max_discount_rate else 0
        )
        discounted_price = (
            int(menu.menu_price * (1 - item.max_discount_rate))
            if item.max_discount_rate
            else menu.menu_price
        )

        data = {
            "store_name": store.store_name,
            "store_address": store_address,
            "store_image_url": store.store_image_url,
            "store_description": store.store_description,
            "selected_time": selected_time,
            "distance": distance,
            "on_foot": on_foot,
            "is_liked": is_liked,
            "liked_id": liked_id,
            "menu_id": menu.menu_id,
            "menu_name": menu.menu_name,
            "menu_image_url": menu.menu_image_url,
            "item_id": item.item_id,
            "discount_rate": discount_rate_percent,
            "discounted_price": discounted_price,
            "menu_price": menu.menu_price,
        }
        return Response(data)


# 가짜 주소 Store 갱신하기
class MakeAddress(APIView):
    permission_classes = [IsAdminRole]

    @swagger_auto_schema(
        operation_summary="User 주소 업데이트",
        operation_description="User 본인의 도로명 주소(user_address)를 업데이트합니다.",
        responses={200: "주소 수정 완료", 401: "인증이 필요합니다."},
    )
    def patch(self, request):
        stores = Store.objects.all()

        stores_to_update = []
        for store in stores:
            store_address = store.store_address
            new_address = change_to_cau(store_address)

            if new_address is None:
                continue

            store.store_address = new_address
            # store.save()
            stores_to_update.append(store)  # DB 효율 위해 모아놨다가 한번에 업데이트

        Store.objects.bulk_update(stores_to_update, ["store_address"])

        return Response({"message" : "주소 수정 완료"})

# 공급자 API -----------------------------------------------

# 공급자용 가게 등록/조회 하기
class OwnerStore(APIView):
    permission_classes = [IsOwnerRole]

    @swagger_auto_schema(
        operation_summary="Owner 자기 Store 등록",
        operation_description="store_owner 에 본인을 등록합니다.",
        responses={200: "가게 등록 완료", 401: "인증이 필요합니다.", 403: "권한이 없습니다",404 : "해당 store_id 의 store가 존재하지 않음"}
    )
    def post(self,request):
        user = request.user
        if not user or not user.is_authenticated :
            return Response({"error : 인증이 필요합니다."}, status = 401)
        
        
        
        store_id = request.data.get("store_id")
        if not store_id:
            return Response ({"error": "store_id가 필요합니다."}, status=400)
        store = get_object_or_404(Store, store_id=store_id)

        store.store_owner = user
        store.save()

        return Response({
            "message": "가게 등록 성공",
            "store_id" : store.store_id,
            "store_name" : store.store_name,
            "store_category": store.store_category,
            "store_address": store.store_address,
            "store_image_url": store.store_image_url,
            "store_description" : store.store_description
        }, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_summary="Owner 자기 Store 조회",
        operation_description="Owner 본인의 가게 정보를 조회합니다.",
        responses={200: "가게 조회 완료", 401: "인증이 필요합니다.", 403: "권한이 없습니다", 404 : "해당 owner의 store가 존재하지 않음"}
    )
    def get(self, request):
        user = request.user
        if not user or not user.is_authenticated :
            return Response({"error : 인증이 필요합니다."}, status = 401)
        
        

        store = get_object_or_404(Store, store_owner = user)

        return Response({
            "store_id" : store.store_id,
            "store_name" : store.store_name,
            "store_category": store.store_category,
            "store_address": store.store_address,
            "store_image_url": store.store_image_url,
            "store_description" : store.store_description
        }, status=status.HTTP_200_OK)
    
# 공급자용 슬롯 확인하기
class OwnerSlot(APIView):
    permission_classes = [IsOwnerRole]

    def get(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)

        store_id = request.data.get("store_id")
        if not store_id:
            return Response({"error": "store_id가 필요합니다."}, status=400)

        # store_id에 해당하는 모든 space 정보 가져오기
        try:
            spaces = StoreSpace.objects.filter(store_id=store_id)
        except Store.DoesNotExist:
            return Response({"error": "해당하는 스토어를 찾을 수 없습니다."}, status=404)

        today = date.today()
        tomorrow = today + timedelta(days=1)
        now = datetime.now().time()

        today_spaces_data = []
        tomorrow_spaces_data = []

        # 슬롯 데이터를 처리하는 헬퍼 함수
        def process_slots(slot_queryset):
            slots_data = []
            for slot in slot_queryset:
                reservation_info = None
                is_reserved = False

                # 예약이 있는지 확인
                try:
                    reservation = Reservation.objects.get(reservation_slot=slot)
                    is_reserved = True
                    
                    # 예약이 있을 경우, 예약 정보 구성
                    # reservation.store_item이 ReservationItem 모델에 대한 OneToOne 필드라고 가정
                    reservation_item = reservation.store_item
                    
                    menu_name = None
                    if reservation_item:
                        # 메뉴 이름 가져오기.
                        try:
                            # reservation_item.menu가 Menu 모델에 대한 OneToOne 필드라고 가정
                            menu_name = reservation_item.menu.menu_name
                        except StoreMenu.DoesNotExist:
                            # 관련 메뉴가 없을 경우
                            print(f"Warning: Menu not found for item_id {reservation_item.item_id}")
                            menu_name = None # 또는 "알 수 없는 메뉴"와 같이 설정

                    reservation_info = {
                        "reservation_id": reservation.reservation_id,
                        "item_id": reservation_item.item_id if reservation_item else None,
                        "user_email": reservation.user.user_email,
                        "menu_name": menu_name
                    }
                except Reservation.DoesNotExist:
                    # 예약이 없으면 수동 마감 상태 확인
                    is_reserved = slot.is_reserved

                slots_data.append({
                    "slot_id": slot.slot_id,
                    "time": slot.slot_reservation_time.strftime("%H:%M"),
                    "is_reserved": is_reserved,
                    "reservation_info": reservation_info,
                })
            return slots_data

        for space in spaces:
            # 오늘 슬롯 (현재 시간 이후)
            today_slots = StoreSlot.objects.filter(
                space=space,
                slot_reservation_date=today,
                slot_reservation_time__gte=now
            ).order_by('slot_reservation_time')
            today_slots_data = process_slots(today_slots)
            
            today_spaces_data.append({
                "space_id": space.space_id,
                "space_name": space.space_name,
                "space_image_url": space.space_image_url,
                "slots": today_slots_data
            })

            # 내일 슬롯
            tomorrow_slots = StoreSlot.objects.filter(
                space=space,
                slot_reservation_date=tomorrow
            ).order_by('slot_reservation_time')
            tomorrow_slots_data = process_slots(tomorrow_slots)

            tomorrow_spaces_data.append({
                "space_id": space.space_id,
                "space_name": space.space_name,
                "space_image_url": space.space_image_url,
                "slots": tomorrow_slots_data
            })
        
        response_data = {
            "dates": [
                {
                    "date": "today",
                    "spaces": today_spaces_data
                },
                {
                    "date": "tomorrow",
                    "spaces": tomorrow_spaces_data
                }
            ]
        }
        return Response(response_data)