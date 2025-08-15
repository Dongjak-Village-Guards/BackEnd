from django.shortcuts import render

from rest_framework.response import Response
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Max, Q
from django.utils import timezone
import datetime
from django.db import transaction

# 모델
from .models import *
from accounts.models import User
from stores.models import * 

# 시리얼라이저
from .serializers import *

# 권한
from accounts.permissions import *

# Create your views here.

# ----------------------------
# Reservation API
# ----------------------------
class ReserveList(APIView):
    permission_classes = [IsUserRole]
    
    # 예약 생성
    @swagger_auto_schema(
        operation_summary="Reservation 생성",
        operation_description="해당 item_id로 새로운 Reservation을 생성합니다.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "item_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="예약할 StoreItem ID")
            },
            required=["item_id"]
        ),
        responses={
            201: openapi.Response(
                description="예약 성공",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "reservation_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "store_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "reservation_date": openapi.Schema(type=openapi.TYPE_STRING, format="date"),
                        "reservation_time": openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            ),
            400: "item_id 누락 or 예약 불가",
            401: "인증이 필요합니다.",
            404: "존재하지 않는 Item or StoreSlot"
        }
    )
    def post(self, request):
        user = request.user  # JWT 인증으로 이미 로그인한 사용자 객체가 들어있음
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)
        
        item_id = request.data.get('item_id')
        if not item_id:
            return Response({"error": "item_id 가 필요합니다."}, status = 400)

        with transaction.atomic(): # 블록 안이 전부 성공하면 커밋, 실패하면 롤백.
            item = get_object_or_404(StoreItem.objects.select_for_update(), item_id=item_id) # DB 레벨에서 해당 row를 잠금(lock) 걸어서 동시 예약 문제 방지
        
            # 이미 예약 했는지 확인 (재고가 0인 지 = 예약 불가)
            if item.item_stock == 0:
                return Response({"error": "예약이 불가능한 상품입니다."}, status=400)

            # StoreSlot 확인
            store_slot = get_object_or_404(StoreSlot, space = item.space, slot_reservation_date = item.item_reservation_date, slot_reservation_time = item.item_reservation_time)
            if store_slot.is_reserved == True:
                return Response({"error" : "예약이 불가능한 상품입니다."}, status=400)
        
            # 재고 차감
            item.item_stock -= 1
            item.save()

            # StoreSlot 상태 변경
            store_slot.is_reserved = True
            store_slot.save()

            # 할인 금액 계산하기
            menu = item.menu
            price_original = menu.menu_price
            discounted_cost = price_original - price_original*item.current_discount_rate
        
            # 예약 생성
            reservation = Reservation.objects.create(user=user, store_item=item, reservation_slot = store_slot, reservation_cost = discounted_cost)
        
		    # 할인 금액 계산 및 저장
            user.user_discounted_cost_sum += reservation.reservation_cost
            user.save()
    
        return Response({
            "reservation_id": reservation.reservation_id,
            "store_name": reservation.store_item.store.store_name,
            "reservation_date": reservation.reservation_slot.slot_reservation_date,
            "reservation_time": f"{reservation.reservation_slot.slot_reservation_time}:00"
        }, status=201)


class ReserveDetail(APIView):
    permission_classes = [IsUserRole]

    # 예약 삭제
    @swagger_auto_schema(
        operation_summary = "Reservation 삭제",
        operation_description = "해당 id의 예약을 취소합니다.",
        responses={204: "삭제 완료", 400: "reservation_id 가 필요합니다.", 401: "인증이 필요합니다.", 403: "권한이 없습니다.", 404: "존재하지 않는 reservation_id"}
    )
    def delete(self, request):
        user = request.user  # JWT 인증으로 이미 로그인한 사용자 객체가 들어있음
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)
        
        reservation_id = request.data.get('reservation_id')
        if not reservation_id:
            return Response({"error": "reservation_id 가 필요합니다."}, status = 400)

        reservation = get_object_or_404(Reservation, reservation_id=reservation_id)

        # 예약 취소 권한 검사 (본인인지)
        if user.user_role == "admin":
            pass
        elif user != reservation.user : 
            return Response({"error" : "권한이 없습니다."}, status = 403)

        # 예약 시간이 reservation.reservation_slot_id의 예약 날짜+시간
        slot = reservation.reservation_slot
        if not slot or not slot.slot_reservation_date or not slot.slot_reservation_time:
            return Response({"error": "예약 시간이 올바르지 않습니다."}, status=400)

        # 예약 datetime 생성
        reservation_datetime = datetime.datetime.combine(slot.slot_reservation_date, datetime.time(hour=slot.slot_reservation_time))
        reservation_datetime = timezone.make_aware(reservation_datetime)
        now = timezone.now()

        # 30분 전인지 확인
        if reservation_datetime - now < datetime.timedelta(minutes=30):
            return Response({"error": "예약 취소는 예약 30분 전까지 가능합니다."}, status=400)
		
		# User의 discounted_cost_sum 수정
        user.user_discounted_cost_sum -= reservation.reservation_cost
        user.save()
		
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
        responses={200: ReservationSerializer(many=True), 401: "인증이 필요합니다."}
    )
    def get(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)

        # select_related로 N+1 문제 방지
        reservations = Reservation.objects.filter(user_id=user).select_related(
            'reservation_slot', 'store_item', 'store_item__store',
            'store_item__menu', 'store_item__space'
        ).order_by(
            'reservation_slot__slot_reservation_date', 
            'reservation_slot__slot_reservation_time'
        )

        serializer = ReservationSerializer(reservations, many=True)
        return Response(serializer.data)
    


# ----------------------------
# UserLike API
# ----------------------------
class LikeDetail(APIView):
    permission_classes = [IsUserRole]

    # 좋아요 생성
    @swagger_auto_schema(
        operation_summary = "좋아요 생성",
        operation_description = "새로운 좋아요를 생성합니다.",
        responses={201: UserLikeSerializer, 400: "store_id 누락 or 이미 좋아요함", 401: "인증이 필요합니다.", 404 : "존재하지 않는 Store"}
    )
    def post(self, request):
        user = request.user  # JWT 인증으로 이미 로그인한 사용자 객체가 들어있음
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)
        
        store_id = request.data.get('store_id')
        if not store_id:
            return Response({"error": "store_id 가 필요합니다."}, status = 400)

        store = get_object_or_404(Store, store_id=store_id)
    
        # 이미 좋아요 했는지 확인
        if UserLike.objects.filter(user=user, store=store).exists():
            return Response({"error": "이미 좋아요를 눌렀습니다."}, status=400)

        # 좋아요 생성
        like = UserLike.objects.create(user=user, store=store)
        # 난 처음에 user_id = user_id 이렇게 적어야 하는줄 알았는데 외래키라서 실제 UserLike 모델의 user_id에는 User 객체가 들어간대...
    
        serializer = UserLikeSerializer(like)
        return Response(serializer.data, status = 201)
    
    # 좋아요 조회
    @swagger_auto_schema(
        operation_summary="업종별 매장 목록 조회",
        operation_description="선택한 업종(category_filter)에 따라 매장을 필터링해서 반환합니다.",
        manual_parameters=[
            openapi.Parameter(
                'category_filter', openapi.IN_QUERY, 
                description="필터할 업종 이름", 
                type=openapi.TYPE_STRING, required=False
            )
        ],
        responses={200: UserLikeSerializer(many=True), 401 : "error : 인증이 필요합니다."}
    )
    def get(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)

        time_filter = request.query_params.get("time")
        category_filter = request.query_params.get("store_category")

        # 기본 시간: 현재 시간의 정각
        if not time_filter:
            time_filter = datetime.datetime.now().hour
        else:
            time_filter = int(time_filter)

        # 찜한 매장 가져오기
        user_likes = UserLike.objects.filter(user=user).select_related('store').order_by('created_at')

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
                item_reservation_time=time_filter,
                item_stock__gt=0
            ).select_related('menu')

            is_available = items.exists()

            # 최대 할인 메뉴 찾기
            max_discount_item = items.order_by('-current_discount_rate').first() if is_available else None

            result.append({
                "like_id": like.like_id,
                "user_id": user.id,
                "store_id": store.store_id,
                "created_at": like.created_at,
                "store_name": store.store_name,
                "distance": 100,  # 실제 거리 계산 로직 필요
                "on_foot": 30,  # 실제 도보 시간 계산 로직 필요
                "store_image_url": store.store_image_url,
                "menu_name": max_discount_item.menu.menu_name if max_discount_item else None,
                "menu_id": max_discount_item.menu.menu_id if max_discount_item else None,
                "max_discount_rate": max_discount_item.current_discount_rate if max_discount_item else None,
                "max_discount_menu": max_discount_item.menu.menu_name if max_discount_item else None,
                "max_discount_price_origin": max_discount_item.menu.menu_price if max_discount_item else None,
                "max_discount_price": max_discount_item.menu.menu_price * (1 - max_discount_item.current_discount_rate) if max_discount_item else None,
                "is_liked": True,
                "is_available": is_available
            })

        return Response(result, status=200)
    
    # 좋아요 삭제
    permission_classes = [IsUserRole]
    @swagger_auto_schema(
        operation_summary = "좋아요 삭제",
        operation_description = "해당 id의 좋아요를 삭제합니다.",
        responses={204: "삭제 완료", 400: "like_id 가 필요합니다.", 401: "인증이 필요합니다.", 403: "권한이 없습니다.", 404: "존재하지 않는 like_id"}
    )
    def delete(self, request):
        user = request.user  # JWT 인증으로 이미 로그인한 사용자 객체가 들어있음
        if not user or not user.is_authenticated:
            return Response({"error": "인증이 필요합니다."}, status=401)
        
        like_id = request.data.get('like_id')
        if not like_id:
            return Response({"error": "like_id 가 필요합니다."}, status = 400)

        like = get_object_or_404(UserLike, like_id=like_id)

        # 좋아요 삭제 권한 검사
        if user.user_role == "admin":
            pass
        elif user != like.user_id : # 이것도 like.user_id 라고 하면 이게 FK니까 user 객체가 온대.
            return Response({"error" : "권한이 없습니다."}, status = 403)
    
        # 좋아요 삭제
        like.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
