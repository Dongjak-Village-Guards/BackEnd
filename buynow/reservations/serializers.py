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

    def get_reservation_time(self, obj):
        return f"{obj.reservation_slot.slot_reservation_time:02}:00"


class UserLikeSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only = True)
    store_id = serializers.IntegerField(source='store.store_id', read_only = True)

    class Meta:
        model = User
        fields = [
            "like_id",
            "user_id",
            "store_id",
            "created_at"
        ]
