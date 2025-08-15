from rest_framework import serializers
from accounts.models import User
from stores.models import Store,StoreItem
from .models import *
from django.conf import settings
import os, json


class ReservationSerializer(serializers.ModelSerializer):
    store_id = serializers.IntegerField(source='store_item.store.store_id')
    store_name = serializers.CharField(source='store_item.store.store_name')
    store_image_url = serializers.CharField(source='store_item.store.store_image_url')
    space_name = serializers.CharField(source='store_item.space.space_name')
    menu_name = serializers.CharField(source='store_item.menu.menu_name')
    reservation_date = serializers.DateField(source='reservation_slot.slot_reservation_date', format='%Y-%m-%d')
    reservation_time = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            'reservation_id', 'store_id', 'store_name', 'store_image_url',
            'reservation_date', 'reservation_time', 'space_name', 'menu_name'
        ]

    def get_store_id(self, obj):
        if not obj.store_item or not obj.store_item.store:
            raise serializers.ValidationError("예약에 연결된 매장이 없습니다.")
        return obj.store_item.store.store_id

    def get_store_name(self, obj):
        if not obj.store_item or not obj.store_item.store:
            raise serializers.ValidationError("예약에 연결된 매장이 없습니다.")
        return obj.store_item.store.store_name

    def get_store_image_url(self, obj):
        if not obj.store_item or not obj.store_item.store:
            raise serializers.ValidationError("예약에 연결된 매장이 없습니다.")
        return obj.store_item.store.store_image_url

    def get_space_name(self, obj):
        if not obj.store_item or not obj.store_item.space:
            raise serializers.ValidationError("예약에 연결된 공간이 없습니다.")
        return obj.store_item.space.space_name

    def get_menu_name(self, obj):
        if not obj.store_item or not obj.store_item.menu:
            raise serializers.ValidationError("예약에 연결된 메뉴가 없습니다.")
        return obj.store_item.menu.menu_name

    def get_reservation_date(self, obj):
        if not obj.reservation_slot:
            raise serializers.ValidationError("예약 슬롯 정보가 없습니다.")
        return obj.reservation_slot.slot_reservation_date

    def get_reservation_time(self, obj):
        if not obj.reservation_slot or obj.reservation_slot.slot_reservation_time is None:
            raise serializers.ValidationError("예약 시간이 올바르지 않습니다.")
        return f"{obj.reservation_slot.slot_reservation_time:02}:00"

class UserLikeSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only = True)
    store_id = serializers.IntegerField(source='store.store_id', read_only = True)

    class Meta:
        model = UserLike
        fields = [
            "like_id",
            "user_id",
            "store_id",
            "created_at"
        ]
    def validate(self, data):
        """
        전역 유효성 검사 - User와 Store가 정상적으로 연결되는지, 
        중복 좋아요가 아닌지 체크
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError({"error": "인증이 필요합니다."})

        store = self.context.get('store')
        if not store:
            raise serializers.ValidationError({"error": "유효한 store_id가 필요합니다."})

        # 이미 좋아요가 존재하는 경우
        if UserLike.objects.filter(user=request.user, store=store).exists():
            raise serializers.ValidationError({"error": "이미 좋아요를 눌렀습니다."})

        return data
