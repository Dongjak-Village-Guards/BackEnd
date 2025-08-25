from django.shortcuts import render

from rest_framework.response import Response
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Max, Q
from django.utils import timezone

# import datetime, time
import datetime
from datetime import datetime, timedelta, date, time
from django.db import transaction
from config.kakaoapi import get_distance_walktime
from pricing.utils import create_item_record, safe_create_item_record

# 모델
from .models import *
from accounts.models import User
from stores.models import *

# 시리얼라이저
from .serializers import *

# 권한
from accounts.permissions import *

# 예외 처리 구문 추가
from django.db import IntegrityError, transaction
from rest_framework import status

# 로깅 파일
from logger import get_logger

logger = get_logger("buynow.reservations")


def view_func(request):
    logger.info("배포 서버에서 호출됨")
    try:
        1 / 0
    except Exception as e:
        logger.error(f"에러 발생: {e}")


# Reservation API
class ReserveList(APIView):
    permission_classes = [IsUserRole]

    # 예약 생성
    @swagger_auto_schema(
        operation_summary="Reservation 생성",
        operation_description="해당 item_id로 새로운 Reservation을 생성합니다.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "item_id": openapi.Schema(
                    type=openapi.TYPE_INTEGER, description="예약할 StoreItem ID"
                )
            },
            required=["item_id"],
        ),
        responses={
            201: openapi.Response(
                description="예약 성공",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "reservation_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "store_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "reservation_date": openapi.Schema(
                            type=openapi.TYPE_STRING, format="date"
                        ),
                        "reservation_time": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
            400: "item_id 누락 or 예약 불가 or 시간 지난 item or 가격,할인율 누락",
            401: "인증이 필요합니다.",
            404: "존재하지 않는 Item or StoreSlot",
        },
    )
    def post(self, request):
        try:
            user = request.user
            if not user or not user.is_authenticated:
                return Response({"error": "인증이 필요합니다."}, status=401)

            item_id = request.data.get("item_id")
            if not item_id:
                return Response({"error": "item_id 가 필요합니다."}, status=400)

            # 타입 검사
            try:
                item_id = int(item_id)
            except (TypeError, ValueError):
                return Response({"error": "item_id는 정수여야 합니다."}, status=400)

            with transaction.atomic():
                # 해당 아이템 락 걸어서 조회
                item = get_object_or_404(
                    StoreItem.objects.select_for_update(), item_id=item_id
                )

                # 현재 시간보다 이전 예약이면 예약 불가
                item_datetime = datetime.combine(
                    item.item_reservation_date, time(hour=item.item_reservation_time)
                )
                if timezone.make_aware(item_datetime) <= timezone.now():
                    return Response(
                        {"error": "이미 지난 시간은 예약할 수 없습니다."}, status=400
                    )

                # 재고 확인
                if item.item_stock <= 0:
                    return Response(
                        {"error": "예약이 불가능한 상품입니다."}, status=400
                    )

                # 슬롯 확인 - 가게측에서 가능한 지
                store_slot = get_object_or_404(
                    StoreSlot,
                    space=item.space,
                    slot_reservation_date=item.item_reservation_date,
                    slot_reservation_time=item.item_reservation_time,
                )
                if store_slot.is_reserved:
                    return Response({"error": "이미 예약된 슬롯입니다."}, status=400)

                # 슬롯 확인 - 손님측에서 이전에 이시간에 예약을 했는 지
                exists = Reservation.objects.filter(
                    user=user,
                    reservation_slot__slot_reservation_date=item.item_reservation_date,
                    reservation_slot__slot_reservation_time=item.item_reservation_time,
                ).exists()

                if exists:
                    return Response(
                        {"error": "동일 시간대에 이미 예약을 한 상태입니다"},
                        status=400,
                    )

                # 재고 차감
                item.item_stock -= 1
                item.save()

                # 슬롯 예약 상태 변경
                store_slot.is_reserved = True
                store_slot.save()

                # 할인 금액 계산
                menu = item.menu
                price_original = menu.menu_price
                if price_original is None or item.current_discount_rate is None:
                    return Response(
                        {"error": "가격 또는 할인율 정보가 없습니다."}, status=400
                    )
                discounted_cost = (
                    price_original
                    * item.current_discount_rate  # 원가 * 할인율 = 할인된 금액
                )

                # 예약 생성
                reservation = Reservation.objects.create(
                    user=user,
                    store_item=item,
                    reservation_slot=store_slot,
                    reservation_cost=discounted_cost,
                )
                safe_create_item_record(item, sold=1, is_dummy_flag=False)

                # 유저 할인 총액 갱신
                user.user_discounted_cost_sum = (
                    user.user_discounted_cost_sum or 0
                ) + reservation.reservation_cost
                user.save()

            return Response(
                {
                    "reservation_id": reservation.reservation_id,
                    "store_name": reservation.store_item.store.store_name,
                    "reservation_date": reservation.reservation_slot.slot_reservation_date,
                    "reservation_time": f"{reservation.reservation_slot.slot_reservation_time}:00",
                },
                status=201,
            )

        except IntegrityError:
            # 동시성 문제 또는 DB 무결성 오류
            return Response({"error": "동일한 상품이 이미 예약되었습니다."}, status=400)

        except Exception as e:
            # 예기치 못한 오류 로깅
            logger.exception("예약 생성 중 예외 발생")
            return Response(
                {"error": "서버 내부 오류가 발생했습니다.", "detail": str(e)},
                status=500,
            )


class ReserveDetail(APIView):
    permission_classes = [IsUserRole]

    # 예약 삭제
    @swagger_auto_schema(
        operation_summary="Reservation 삭제",
        operation_description="해당 id의 예약을 취소합니다.",
        responses={
            204: "삭제 완료",
            400: "reservation_id 가 필요합니다.",
            401: "인증이 필요합니다.",
            403: "권한이 없습니다.",
            404: "존재하지 않는 reservation_id",
        },
    )
    def delete(self, request, reservation_id):
        user = request.user  # JWT 인증으로 이미 로그인한 사용자 객체가 들어있음
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)

        if not reservation_id:
            return Response({"error": "reservation_id 가 필요합니다."}, status=400)

        reservation = get_object_or_404(Reservation, reservation_id=reservation_id)

        # 예약 취소 권한 검사 (본인인지)
        if user.user_role == "admin":
            pass
        elif user != reservation.user:
            return Response({"error": "권한이 없습니다."}, status=403)

        # 예약 시간이 reservation.reservation_slot_id의 예약 날짜+시간
        slot = reservation.reservation_slot
        if not slot:
            return Response({"error": "slot이 존재하지않습니다."}, status=400)
        if not slot.slot_reservation_date:
            return Response(
                {"error": "slot_reservation_date 가 존재하지않음."}, status=400
            )
        if slot.slot_reservation_time is None:
            return Response(
                {"error": "slot_reservation_time 가 존재하지않음."}, status=400
            )

        # 예약 datetime 생성
        reservation_datetime = datetime.combine(
            slot.slot_reservation_date, time(hour=slot.slot_reservation_time)
        )
        reservation_datetime = timezone.make_aware(reservation_datetime)
        now = timezone.now()

        # 30분 전인지 확인 - 에러코드 추가
        if reservation_datetime - now < timedelta(minutes=30):
            return Response(
                {
                    "errorCode": "CANCELLATION_NOT_ALLOWED",
                    "message": "예약 시작 30분 이내에는 취소가 불가능합니다.",
                },
                status=400,
            )

        # User의 discounted_cost_sum 수정
        user.user_discounted_cost_sum -= reservation.reservation_cost
        user.save()

        # item
        item = reservation.store_item

        # 재고 원상복구
        item.item_stock += 1
        item.save()

        # 예약 삭제
        reservation.delete()

        # Store Slot 상태 변경
        slot.is_reserved = False
        slot.save()

        return Response(status=status.HTTP_204_NO_CONTENT)


class ReserveMe(APIView):
    permission_classes = [IsUserRole]

    # 예약 본인 조회
    @swagger_auto_schema(
        operation_summary="예약 목록 조회",
        operation_description="User 본인의 예약목록을 조회합니다.",
        responses={200: ReservationSerializer(many=True), 401: "인증이 필요합니다."},
    )
    def get(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)

        # 시간 관련
        now = timezone.localtime()
        today = now.date()
        current_hour = now.hour

        # select_related로 N+1 문제 방지
        reservations = (
            Reservation.objects.filter(user=user)
            .select_related(
                "reservation_slot",
                "store_item",
                "store_item__store",
                "store_item__menu",
                "store_item__space",
            )
            .filter(
                Q(reservation_slot__slot_reservation_date__gt=today)
                | Q(
                    reservation_slot__slot_reservation_date=today,
                    reservation_slot__slot_reservation_time__gte=current_hour,
                )
            )
            .order_by(
                "reservation_slot__slot_reservation_date",
                "reservation_slot__slot_reservation_time",
            )
        )

        serializer = ReservationSerializer(reservations, many=True)
        return Response(serializer.data)


# UserLike API
class LikeDetail(APIView):
    permission_classes = [IsUserRole]

    # 좋아요 생성
    @swagger_auto_schema(
        operation_summary="좋아요 생성",
        operation_description="새로운 좋아요를 생성합니다.",
        responses={
            201: UserLikeSerializer,
            400: "store_id 누락 or 이미 좋아요함",
            401: "인증이 필요합니다.",
            404: "존재하지 않는 Store",
        },
    )
    def post(self, request):
        user = request.user  # JWT 인증으로 이미 로그인한 사용자 객체가 들어있음
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)

        store_id = request.data.get("store_id")
        if not store_id:
            return Response({"error": "store_id 가 필요합니다."}, status=400)

        try:
            # Store 존재 여부 확인
            store = get_object_or_404(Store, store_id=store_id)

            # 이미 좋아요 했는지 확인
            if UserLike.objects.filter(user=user, store=store).exists():
                return Response(
                    {"error": "이미 좋아요를 눌렀습니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 트랜잭션 블록 - 도중에 문제 생기면 롤백
            with transaction.atomic():
                like = UserLike.objects.create(user=user, store=store)

        except IntegrityError:
            # DB 제약조건 위반 (중복 좋아요, 잘못된 FK 등)
            return Response(
                {"error": "이미 좋아요했거나 유효하지 않은 store_id입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            # 예상 못한 오류는 서버 에러로 반환
            return Response(
                {"error": f"서버 오류가 발생했습니다: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        serializer = UserLikeSerializer(like)
        return Response(serializer.data, status=201)

    # 좋아요 조회
    @swagger_auto_schema(
        operation_summary="업종별 매장 목록 조회",
        operation_description="선택한 업종(category_filter)에 따라 매장을 필터링해서 반환합니다.",
        manual_parameters=[
            openapi.Parameter(
                "category_filter",
                openapi.IN_QUERY,
                description="필터할 업종 이름",
                type=openapi.TYPE_STRING,
                required=False,
            )
        ],
        responses={
            200: UserLikeSerializer(many=True),
            401: "error : 인증이 필요합니다.",
        },
    )
    def get(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)

        time_param = request.query_params.get("time")
        category_filter = request.query_params.get("store_category")

        # time_filter 값에 따라 날짜와 시간을 동적으로 설정
        try:
            if time_param is not None:
                time_filter = int(time_param)
                if not 0 <= time_filter <= 36:
                    return Response(
                        {
                            "error": "유효하지 않은 시간 값입니다. 0부터 36 사이의 값을 입력해주세요."
                        },
                        status=400,
                    )
            else:
                time_filter = datetime.now().hour
        except ValueError:
            return Response({"error": "시간 값은 정수여야 합니다."}, status=400)

        # 요청된 시간에 따라 예약 날짜를 계산
        if time_filter >= 24:
            reservation_date = date.today() + timedelta(days=1)
            # StoreItem 예약 시간은 0-23시 기준이므로, 24를 빼서 다음날의 시간으로 변환
            reservation_time_for_items = time_filter - 24
        else:
            reservation_date = date.today()
            reservation_time_for_items = time_filter

        # 찜한 매장 가져오기
        user_likes = (
            UserLike.objects.filter(user=user)
            .select_related("store")
            .order_by("created_at")
        )

        # 응답용 리스트
        result = []

        for like in user_likes:
            store = like.store

            # 업종 필터 적용
            if category_filter and store.store_category != category_filter:
                continue

            # StoreItem에서 예약 가능 여부 확인

            items = StoreItem.objects.filter(
                store=store,
                item_reservation_date=reservation_date,
                item_reservation_time=reservation_time_for_items,
                item_stock__gt=0,
            ).select_related("menu")

            # 모든 space의 slot중 time_filter에 해당하는 거 찾고, 그 slot의 is_reserved가 다 true면 is_available은 false
            is_available = False

            spaces = StoreSpace.objects.filter(store=store)
            for space in spaces:
                slot = get_object_or_404(
                    StoreSlot,
                    space=space,
                    slot_reservation_date=reservation_date,
                    slot_reservation_time=reservation_time_for_items,
                )
                if slot.is_reserved == False:
                    is_available = True
                    break

            # 최대 할인 메뉴 찾기
            max_discount_item = (
                items.order_by("-current_discount_rate").first()
                if is_available
                else None
            )

            # 거리 와 도보시간
            distance, on_foot = get_distance_walktime(
                store.store_address, user.user_address
            )

            discounted_price = (
                int(
                    (
                        max_discount_item.menu.menu_price
                        * (1 - max_discount_item.current_discount_rate)
                    )
                    // 100
                    * 100
                )
                if max_discount_item.current_discount_rate
                and max_discount_item.current_discount_rate > 0
                else max_discount_item.menu.menu_price
            )

            result.append(
                {
                    "like_id": like.like_id,
                    "user_id": user.id,
                    "store_id": store.store_id,
                    "created_at": like.created_at,
                    "store_name": store.store_name,
                    "distance": distance,
                    "on_foot": on_foot,
                    "store_image_url": store.store_image_url,
                    "menu_name": (
                        max_discount_item.menu.menu_name if max_discount_item else None
                    ),
                    "menu_id": (
                        max_discount_item.menu.menu_id if max_discount_item else None
                    ),
                    "max_discount_rate": (
                        max_discount_item.current_discount_rate
                        if max_discount_item
                        else None
                    ),
                    "max_discount_menu": (
                        max_discount_item.menu.menu_name if max_discount_item else None
                    ),
                    "max_discount_price_origin": (
                        max_discount_item.menu.menu_price if max_discount_item else None
                    ),
                    "max_discount_price": discounted_price,
                    "is_liked": True,
                    "is_available": is_available,
                }
            )

        return Response(result, status=200)

    # 좋아요 삭제
    permission_classes = [IsUserRole]

    @swagger_auto_schema(
        operation_summary="좋아요 삭제",
        operation_description="해당 id의 좋아요를 삭제합니다.",
        responses={
            204: "삭제 완료",
            400: "like_id 가 필요합니다.",
            401: "인증이 필요합니다.",
            403: "권한이 없습니다.",
            404: "존재하지 않는 like_id",
        },
    )
    def delete(self, request):
        user = request.user  # JWT 인증으로 이미 로그인한 사용자 객체가 들어있음
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)

        like_id = request.data.get("like_id")
        if not like_id:
            return Response({"error": "like_id 가 필요합니다."}, status=400)

        like = get_object_or_404(UserLike, like_id=like_id)

        # 좋아요 삭제 권한 검사
        if user.user_role == "admin":
            pass
        elif (
            user != like.user
        ):  # 이것도 like.user_id 라고 하면 이게 FK니까 user 객체가 온대.
            return Response({"error": "권한이 없습니다."}, status=403)

        # 좋아요 삭제
        like.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# 공급자 관련 api
# 공급자용 예약 조회, 예약 취소
class OwnerReservation(APIView):
    permission_classes = [IsOwnerRole]

    # 예약 조회
    def get(self, request, store_id):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)

        store = get_object_or_404(Store, store_id=store_id)
        if store.store_owner != user:
            return Response({"error": "가게 주인이 아닙니다."}, status=403)

        # store_id에 해당하는 모든 space 정보 가져오기
        try:
            spaces = StoreSpace.objects.filter(store_id=store_id)
        except Store.DoesNotExist:
            return Response(
                {"error": "해당하는 스토어를 찾을 수 없습니다."}, status=404
            )

        today = date.today()
        tomorrow = today + timedelta(days=1)
        now = datetime.now().hour

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
                            print(
                                f"Warning: Menu not found for item_id {reservation_item.item_id}"
                            )
                            menu_name = None  # 또는 "알 수 없는 메뉴"와 같이 설정

                    reservation_info = {
                        "reservation_id": reservation.reservation_id,
                        "item_id": (
                            reservation_item.item_id if reservation_item else None
                        ),
                        "user_email": reservation.user.user_email,
                        "menu_name": menu_name,
                    }
                except Reservation.DoesNotExist:
                    # 예약이 없으면 수동 마감 상태 확인
                    is_reserved = slot.is_reserved

                slots_data.append(
                    {
                        "slot_id": slot.slot_id,
                        "time": time(slot.slot_reservation_time).strftime("%H:%M"),
                        "is_reserved": is_reserved,
                        "reservation_info": reservation_info,
                    }
                )
            return slots_data

        for space in spaces:
            # 오늘 슬롯 (현재 시간 이후)
            today_slots = StoreSlot.objects.filter(
                space=space, slot_reservation_date=today, slot_reservation_time__gte=now
            ).order_by("slot_reservation_time")
            today_slots_data = process_slots(today_slots)

            today_spaces_data.append(
                {
                    "space_id": space.space_id,
                    "space_name": space.space_name,
                    "space_image_url": space.space_image_url,
                    "slots": today_slots_data,
                }
            )

            # 내일 슬롯
            tomorrow_slots = StoreSlot.objects.filter(
                space=space, slot_reservation_date=tomorrow
            ).order_by("slot_reservation_time")
            tomorrow_slots_data = process_slots(tomorrow_slots)

            tomorrow_spaces_data.append(
                {
                    "space_id": space.space_id,
                    "space_name": space.space_name,
                    "space_image_url": space.space_image_url,
                    "slots": tomorrow_slots_data,
                }
            )

        response_data = {
            "today": {"spaces": today_spaces_data},
            "tomorrow": {"spaces": tomorrow_spaces_data},
        }
        return Response(response_data)


# 공급자용 예약 취소
class OwnerReservationDetail(APIView):
    permission_classes = [IsOwnerRole]

    # 예약 취소
    def delete(self, request, slot_id, reservation_id):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)

        slot = get_object_or_404(StoreSlot, slot_id=slot_id)

        if slot.is_reserved == False:  # 예약이 아직 안되어있다는 거니까.
            return Response(
                {"error": "is_reserved 가 false 입니다. 잘못된 요청"}, status=400
            )

        # reservation 가져오기
        reservation = get_object_or_404(
            Reservation, reservation_slot=slot, reservation_id=reservation_id
        )

        with transaction.atomic():
            # 예약한 user의 discounted_cost_sum 돌려놓기
            reservation_user = reservation.user
            reservation_user.user_discounted_cost_sum -= reservation.reservation_cost
            reservation_user.save()

            item = reservation.store_item

            # item 재고 돌려놓기
            item.item_stock += 1
            item.save()

            # reservation delete
            reservation.delete()

            # slot 상태 변경하기
            slot.is_reserved = False
            slot.save()

        return Response({"message": "예약 취소 성공"}, status=200)


# 공급자용 make slot closed
class OwnerClosed(APIView):
    permission_classes = [IsOwnerRole]

    def patch(self, request, slot_id):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)

        slot = get_object_or_404(StoreSlot, slot_id=slot_id)

        # 예약 가능한 (예약 안된) slot을 예약 못하게 하는거니까.
        if (
            slot.is_reserved == True
        ):  # True 면 이미 예약이 되어있으니까 이미 예약 못하는거잖아. 그니까 에러.
            return Response(
                {"error": "is_reserved 가 true 입니다. 잘못된 요청"}, status=400
            )

        slot.is_reserved = True
        slot.save()

        return Response(
            {"message": f"{slot.slot_id} closed"}, status=status.HTTP_200_OK
        )


# 공급자용 make slot opened
class OwnerOpen(APIView):
    permission_classes = [IsOwnerRole]

    def patch(self, request, slot_id):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)

        slot = get_object_or_404(StoreSlot, slot_id=slot_id)

        # 수동 마감(예약 안되게끔) 했던 slot을 예약 가능하게 하는거니까.
        if slot.is_reserved == False:  # false 면 이미 예약해도 되는 거니까 잘못된거지.
            return Response(
                {"error": "is_reserved 가 false 입니다. 잘못된 요청"}, status=400
            )

        # 해당 slot을 fk로 가지고 있는 Reservation 데이터가 있는지
        existing_reservation = Reservation.objects.filter(
            reservation_slot=slot
        ).exists()
        if existing_reservation:
            return Response(
                {"error": "이 슬롯과 연결된 예약이 이미 존재합니다. 잘못된 요청"},
                status=400,
            )

        slot.is_reserved = False
        slot.save()

        return Response({"message": f"{slot.slot_id} open"}, status=status.HTTP_200_OK)
