from config.kakaoapi import (
    get_distance_walktime,
    get_coordinates,
    get_distance_walktime_with_coor,
)

from django.shortcuts import render

from accounts.permissions import IsUserRole, IsAdminRole, IsOwnerRole
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db.models import Q, Max, Count, F, ExpressionWrapper, FloatField, Window, Prefetch
from django.db.models.functions import RowNumber
from datetime import datetime, timedelta, date
import math
import requests  # 외부 api 호출용
import random  # 더미 데이터 랜덤 선택용!

from .models import (
    Store,
    StoreItem,
    StoreSpace,
    StoreMenu,
    StoreMenuSpace,
    StoreSlot,
    StoreCoordinate,
)
from reservations.models import UserLike, Reservation
from records.models import ItemRecord
from config.kakaoapi import change_to_cau

from rest_framework import status
from rest_framework.generics import get_object_or_404

# Swagger 관련 import
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from datetime import datetime
from django.db.models import Sum

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
        if not user.user_address:
            return Response(
                {"error": "사용자 주소 정보가 필요합니다."}, status=400
            )  # 주소 필요시 400 반환

        user_x, user_y = get_coordinates(user.user_address)
        user_address = [user_x, user_y]

        # 필수 파라미터 확인할 것!
        try:
            time_filter = int(request.GET.get("time"))
        except (TypeError, ValueError):
            return Response({"error": "Invalid time"}, status=400)
        if not 0 <= time_filter <= 36:
            return Response({"error": "time은 0~36 사이여야 합니다."}, status=400)

        category = request.GET.get("store_category", None)
        today = datetime.now().date()
        target_date = today
        target_time = time_filter
        if time_filter >= 24:
            target_date = today + timedelta(days=1)
            target_time = time_filter - 24

        # 기존 코드에서 1번, 2번, 3번, 4번, 5번 과정을 모두 생략
        # 6번 과정부터 시작
        # StoreItem 조회는 그대로 유지하되, 재고(item_stock)가 0보다 큰 것만 필터링
        base_filters = {
            "item_reservation_date": target_date,
            "item_reservation_time": target_time,
            "store__is_active": True,
        }

        if category:
            normalized_category = category.strip().strip('"')
            if normalized_category != "":
                base_filters["store__store_category__iexact"] = normalized_category

        # 활성화된 아이템만 필터링 (재고 > 0)
        active_items_qs = StoreItem.objects.filter(
            **base_filters, item_stock__gt=0
        ).select_related("store", "menu", "space")

        # 활성화된 Store가 한 개라도 있는 store_id 집합
        active_store_ids = active_items_qs.values_list("store_id", flat=True).distinct()

        # 슬롯이 모두 예약되지 않은 Store의 ID 집합을 구하는 쿼리
        # StoreSlot에서 is_reserved가 False인 슬롯이 하나라도 있는 space를 찾고,
        # 해당 space를 가진 store를 찾습니다.
        available_slot_stores = StoreSlot.objects.filter(
            slot_reservation_date=target_date,
            slot_reservation_time=target_time,
            is_reserved=False,
        ).values_list("space__store_id", flat=True)

        # active_store_ids와 available_slot_stores의 교집합을 구합니다.
        # 이렇게 하면 아이템 재고가 있고, 동시에 예약 가능한 슬롯이 있는 가게만 남게 됩니다.
        final_store_ids = set(active_store_ids) & set(available_slot_stores)

        # 최종적으로 필터링된 아이템 쿼리셋
        filtered_items_qs = active_items_qs.filter(store_id__in=final_store_ids)

        # 각 가게별로 최대 할인 아이템 선택
        ranked_items_qs = (
            filtered_items_qs.annotate(
                discount_amount=ExpressionWrapper(
                    F("menu__menu_price") * F("current_discount_rate"),
                    output_field=FloatField(),
                )  # max -> current
            )
            .annotate(
                rank=Window(
                    expression=RowNumber(),
                    partition_by=[F("store_id")],
                    order_by=[
                        F("discount_amount").desc(),
                        F("menu__menu_price").asc(),
                        F("item_id").asc(),
                    ],
                )
            )
            .select_related("store", "menu")
        )
        final_items = list(ranked_items_qs.filter(rank=1))

        # for문 밖에서 모든 StoreCoordinate, UserLike 정보를 한 번에 가져와 딕셔너리로 저장
        store_coords_dict = {
            item["store_id"]: [item["store_x"], item["store_y"]]
            for item in StoreCoordinate.objects.filter(
                store_id__in=list(final_store_ids)
            ).values("store_id", "store_x", "store_y")
        }

        liked_stores_dict = {
            like.store_id: like.like_id
            for like in UserLike.objects.filter(
                user=user, store_id__in=list(final_store_ids)
            )
        }

        # 4. 루프를 돌면서 한 번에 처리
        results = []

        for item in final_items:
            store = item.store
            store_id = store.store_id

            store_address = store_coords_dict.get(store_id)

            distance = 0
            on_foot = 0
            if user_address and store_address:
                distance_km, walk_time_min = get_distance_walktime_with_coor(
                    store_address, user_address
                )
                distance = int(distance_km * 1000) if distance_km is not None else 0
                on_foot = int(walk_time_min) if walk_time_min is not None else 0

            is_liked = store_id in liked_stores_dict
            liked_id = liked_stores_dict.get(store_id, 0)

            results.append(
                {
                    "store_id": store_id,
                    "store_name": store.store_name,
                    "distance": distance,
                    "on_foot": on_foot,
                    "store_image_url": store.store_image_url,
                    "menu_name": item.menu.menu_name,
                    "menu_id": item.menu.menu_id,
                    "max_discount_rate": int(
                        item.current_discount_rate * 100
                    ),  # max -> current
                    "max_discount_menu": item.menu.menu_name,
                    "max_discount_price_origin": item.menu.menu_price,
                    "max_discount_price": int(
                        (item.menu.menu_price * (1 - item.current_discount_rate))
                        // 100
                        * 100  # 100 단위 절사
                    ),
                    "is_liked": is_liked,
                    "liked_id": liked_id,
                }
            )

        # 마지막으로 거리 오름차순 정렬
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
        user_x, user_y = get_coordinates(user.user_address)
        user_address = [user_x,user_y]

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

        store_coor = get_object_or_404(StoreCoordinate, store_id = store_id)
        store_address = [store_coor.store_x, store_coor.store_y]

        if user_address and store_address:
            distance_km, walk_time_min = get_distance_walktime_with_coor(
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
            # 1) 재고가 1 이상인 아이템 중 최대 할인율 구하기
            max_discount = StoreItem.objects.filter(
                store=store,
                space=space,
                item_reservation_date=target_date,
                item_reservation_time=target_time,
                item_stock__gt=0,  # 재고 1 이상
            ).aggregate(Max("current_discount_rate"))["current_discount_rate__max"]

            # 2) 만약 재고 1 이상인 아이템이 없으면, 재고 0인 아이템 중 최대 할인율 구하기
            if max_discount is None:
                max_discount = StoreItem.objects.filter(
                    store=store,
                    space=space,
                    item_reservation_date=target_date,
                    item_reservation_time=target_time,
                    item_stock=0,  # 재고 0
                ).aggregate(Max("current_discount_rate"))["current_discount_rate__max"]

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

            if is_possible == True:
                slot = get_object_or_404(
                    StoreSlot,
                    space=space,
                    slot_reservation_date=target_date,
                    slot_reservation_time=target_time,
                )
                if slot.is_reserved == True:
                    is_possible = False

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

        # StoreMenuSpace, StoreMenu, StoreItem 정보를 한 번의 쿼리로 미리 가져옴
        menu_spaces = (
            StoreMenuSpace.objects.filter(space=space)
            .select_related("menu")
            .prefetch_related(
                Prefetch(
                    "menu__storeitem_set",
                    queryset=StoreItem.objects.filter(
                        space=space,
                        item_reservation_date=target_date,
                        item_reservation_time=target_time,
                    ).order_by("-current_discount_rate"),
                    to_attr="store_items",
                )
            )
        )

        if not menu_spaces.exists():
            return Response(
                {
                    "errorCode": "NO_MENU_AVAILABLE",
                    "message": "해당 공간에 등록된 메뉴가 없습니다.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # 현재 유저가 이 스토어를 찜했는지 확인
        try:
            like = UserLike.objects.get(user=user, store=store)
            is_liked = True
            liked_id = like.like_id
        except UserLike.DoesNotExist:
            is_liked = False
        liked_id = None

        menus_data = []
        today = datetime.now().date()

        # 각 메뉴별로 해당 시간대에 할인율 높은 순으로 StoreItem 가져오기
        for menu_space in menu_spaces:
            menu = menu_space.menu
            store_items = menu.store_items
        
            if not store_items:
                menus_data.append(
                    {
                        "menu_id": menu.menu_id,
                        "menu_name": menu.menu_name,
                        "menu_image_url": menu.menu_image_url,
                        "menu_price": menu.menu_price,
                        "item_id": None,
                        "discount_rate": 0,
                        "discounted_price": (menu.menu_price // 100) * 100,
                        "is_available": False,
                    }
                )
                continue

            for item in store_items:
                discounted_price = menu.menu_price
                if item.current_discount_rate:
                    discounted_price = int(menu.menu_price * (1 - item.current_discount_rate))
                    discounted_price = (discounted_price // 100) * 100
            
                menus_data.append(
                    {
                        "menu_id": menu.menu_id,
                        "menu_name": menu.menu_name,
                        "menu_image_url": menu.menu_image_url,
                        "menu_price": menu.menu_price,
                        "item_id": item.item_id,
                        "discount_rate": int(item.current_discount_rate * 100) if item.current_discount_rate else 0,
                        "discounted_price": discounted_price,
                        "is_available": item.item_stock > 0,
                    }
                )

        # 6. 최종 응답 반환
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

        return Response(response_data, status=200)

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
                    (int(menu.menu_price * (1 - item.current_discount_rate)) // 100)
                    * 100
                    if item.current_discount_rate
                    else menu.menu_price
                )
                menus_data.append(
                    {
                        "menu_id": menu.menu_id,
                        "menu_name": menu.menu_name,
                        "menu_image_url": menu.menu_image_url,
                        "item_id": item.item_id,
                        "discount_rate": (
                            int(item.current_discount_rate * 100)
                            if item.current_discount_rate
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
            int(item.current_discount_rate * 100) if item.current_discount_rate else 0
        )
        discounted_price = (
            (int(menu.menu_price * (1 - item.current_discount_rate)) // 100) * 100
            if item.current_discount_rate
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
        # store.save()
        stores_to_update.append(store)  # DB 효율 위해 모아놨다가 한번에 업데이트

        Store.objects.bulk_update(stores_to_update, ["store_address"])

        return Response({"message": "주소 수정 완료"})


# 공급자 API


# 공급자용 가게 등록/조회 하기
class OwnerStore(APIView):
    permission_classes = [IsOwnerRole]

    @swagger_auto_schema(
        operation_summary="Owner 자기 Store 등록",
        operation_description="store_owner 에 본인을 등록합니다.",
        responses={
            200: "가게 등록 완료",
            401: "인증이 필요합니다.",
            403: "권한이 없습니다",
            404: "해당 store_id 의 store가 존재하지 않음",
        },
    )
    def post(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"error : 인증이 필요합니다."}, status=401)

        store_id = request.data.get("store_id")
        if not store_id:
            return Response({"error": "store_id가 필요합니다."}, status=400)
        store = get_object_or_404(Store, store_id=store_id)

        store.store_owner = user
        store.save()

        return Response(
            {
                "message": "가게 등록 성공",
                "store_id": store.store_id,
                "store_name": store.store_name,
                "store_category": store.store_category,
                "store_address": store.store_address,
                "store_image_url": store.store_image_url,
                "store_description": store.store_description,
            },
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_summary="Owner 자기 Store 조회",
        operation_description="Owner 본인의 가게 정보를 조회합니다.",
        responses={
            200: "가게 조회 완료",
            401: "인증이 필요합니다.",
            403: "권한이 없습니다",
            404: "해당 owner의 store가 존재하지 않음",
        },
    )
    def get(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"error : 인증이 필요합니다."}, status=401)

        store = get_object_or_404(Store, store_owner=user)

        return Response(
            {
                "store_id": store.store_id,
                "store_name": store.store_name,
                "store_category": store.store_category,
                "store_address": store.store_address,
                "store_image_url": store.store_image_url,
                "store_description": store.store_description,
            },
            status=status.HTTP_200_OK,
        )


class OwnerStatic(APIView):
    permission_classes = [IsOwnerRole]

    def get(self, request, store_id, day):

        try:
            store = get_object_or_404(Store, store_id=store_id)
        except Store.DoesNotExist:
            return Response({"error": "Store not found"}, status=404)

        user = request.user
        if store.store_owner != user:
            return Response({"error": "가게 주인이 아닙니다."}, status=403)

        if day not in [7, 30]:
            return Response(
                {"error": "Invalid 'day' parameter. Must be 7 or 30."}, status=400
            )

        # store_id 로 해당 store의 menu들 다 가져와서 menu들의 리스트 가져오기
        store_menus = StoreMenu.objects.filter(store=store)
        menu_counts = {menu.menu_name: 0 for menu in store_menus}

        # 0~23 리스트 만들기
        hourly_counts = {hour: 0 for hour in range(24)}

        # day가 7인지 30인지에 따라 최근 day일 reservation 정보 필터해서 현재 리스트 전부 가져오기.
        today = datetime.now().date()
        current_period_start = today - timedelta(days=day)
        past_period_start = today - timedelta(days=day * 2)

        current_reservations = Reservation.objects.filter(
            store_item__store=store,
            reservation_slot__slot_reservation_date__range=[
                current_period_start,
                today,
            ],
        ).select_related("store_item__menu", "reservation_slot")

        # day 에 따라 지난 통계 도 가져오기 (과거 리스트)
        past_reservations = Reservation.objects.filter(
            store_item__store=store,
            reservation_slot__slot_reservation_date__range=[
                past_period_start,
                current_period_start - timedelta(days=1),
            ],
        ).select_related("store_item__menu", "reservation_slot")

        # 통계 초기화
        current_total_reservations_count = 0
        current_total_discount_amount = 0
        current_total_price = 0

        # 5. 현재 리스트의 예약 정보 계산
        for res in current_reservations:
            current_total_reservations_count += 1
            current_total_discount_amount += res.reservation_cost

            menu = res.store_item.menu
            if menu:
                # 정가(total_price) 계산
                current_total_price += menu.menu_price

                # 메뉴별 예약 횟수
                if menu.menu_name in menu_counts:
                    menu_counts[menu.menu_name] += 1

            # 시간대별 예약 횟수
            reservation_hour = res.reservation_slot.slot_reservation_time
            if 0 <= reservation_hour < 24:
                hourly_counts[reservation_hour] += 1

        # 6. 과거 리스트의 통계 계산
        past_total_reservations_count = past_reservations.count()
        past_total_discount_amount = (
            past_reservations.aggregate(Sum("reservation_cost"))[
                "reservation_cost__sum"
            ]
            or 0
        )
        past_total_price = (
            sum(
                res.store_item.menu.menu_price
                for res in past_reservations
                if res.store_item.menu
            )
            or 0
        )

        # 7. 최종 수익(total_revenue) 계산
        current_total_revenue = current_total_price - current_total_discount_amount
        past_total_revenue = past_total_price - past_total_discount_amount

        # 8. 성장률(delta) 계산
        def calculate_delta(current, past):
            if past == 0:
                return "-" if current > 0 else 0
            return (current - past) / past * 100

        revenue_delta = calculate_delta(current_total_revenue, past_total_revenue)
        reservations_delta = calculate_delta(
            current_total_reservations_count, past_total_reservations_count
        )

        # 메뉴 통계 딕셔너리를 리스트로 변환
        menu_statistics_list = [
            {"name": name, "count": count} for name, count in menu_counts.items()
        ]

        # count를 기준으로 내림차순 정렬 (큰 값부터)
        menu_statistics_list_sorted = sorted(
            menu_statistics_list, key=lambda x: x["count"], reverse=True
        )

        # time index 랑 당시 할인율 보내기 (7일, 30일 <- created_at으로 확인)
        # 해당 가게의 store_id 로 item id 다 찾고,
        # item_id 로 최근 7/30 일간 (created_at) 생성된 ItemRecord 가져오기 time_offset_idx 랑 record_discount_rate 만.
        # 리스트에 담아서 주기
        # --- 9. time_offset_idx와 record_discount_rate 데이터 구성 --- #
        store_item_ids = StoreItem.objects.filter(store=store).values_list(
            "item_id", flat=True
        )


        day_three = day - 5
        # 최근 day + 3 일 동안 생성된 ItemRecord 가져오기
        record_start_date = today - timedelta(days=day_three)
        item_records = ItemRecord.objects.filter(
            store_item_id__in=store_item_ids,
            created_at__gte=record_start_date,  # BaseModel 상속받았으니 created_at 존재한다고 가정
            record_stock = 0,
            sold = 1,
        ).values("time_offset_idx", "record_discount_rate", "created_at")

        time_dix_discount_rate = [
            {
                "time_offset_idx": rec["time_offset_idx"],
                "discount_rate": rec["record_discount_rate"],
            }
            for rec in item_records
        ]

        # 이 가게에 최대 할인율 구하기
        max_discount_rate = (
            StoreItem.objects.filter(store=store).aggregate(Max("max_discount_rate"))[
                "max_discount_rate__max"
            ]
            or 0
        )

        # JSON 응답 구성
        response_data = {
            "total_revenue": {
                "value": current_total_revenue,
                "delta": (
                    round(revenue_delta, 2)
                    if isinstance(revenue_delta, (int, float))
                    else revenue_delta
                ),
            },
            "total_reservations_count": {
                "value": current_total_reservations_count,
                "delta": (
                    round(reservations_delta, 2)
                    if isinstance(reservations_delta, (int, float))
                    else reservations_delta
                ),
            },
            "total_discount_amount": {"value": current_total_discount_amount},
            "max_discount_rate": {"value": max_discount_rate},
            "time_idx_and_discount_rate": time_dix_discount_rate,
            "menu_statistics": menu_statistics_list_sorted,
            "hourly_statistics": hourly_counts,
        }

        return Response(response_data)

# StoreCoordinate 좌표 채우기 (전체)
class MakeAllCoordinates(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request):
        try:
            stores = Store.objects.all()  # 모든 store 다 가져오기
            for store in stores:
                # 이미 좌표 데이터가 존재하는 지 확인
                if not StoreCoordinate.objects.filter(store_id=store.store_id).exists():
                    address = getattr(store, "store_address", None)
                    if address:
                        x, y = get_coordinates(address)
                        if x and y:
                            StoreCoordinate.objects.create(
                                store_id=store.store_id,
                                store_x=float(x),
                                store_y=float(y),
                            )
                        else:
                            # 좌표 변환 실패 시
                            print(f"좌표 변환 실패:{store.store_name}({address})")
            return Response(
                {"message": "모든 가게의 좌표 데이터 생성을 완료했습니다."},
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# StoreCoordiante 좌표 채우기 (단일) -> 이후 가게 추가하는 상황 고려
class MakeOneCoordinate(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, store_id):
        try:
            store = get_object_or_404(
                Store, store_id=store_id
            )  # 모든 store 다 가져오기
            # 이미 좌표 데이터가 존재하는 지 확인
            if not StoreCoordinate.objects.filter(store_id=store.store_id).exists():
                address = getattr(store, "store_address", None)
                if address:
                    x, y = get_coordinates(address)
                    if x and y:
                        StoreCoordinate.objects.create(
                            store_id=store.store_id, store_x=float(x), store_y=float(y)
                        )
                    else:
                        # 좌표 변환 실패 시
                        print(f"좌표 변환 실패:{store.store_name}({address})")
            return Response(
                {
                    "message": f"store_id : {store.store_id} 인 가게의 좌표 데이터 생성을 완료했습니다."
                },
                status=201,
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
