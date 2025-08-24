# from pricing.models import MenuPricingParam
# from pricing.models import MenuPricingParam
from django.apps import apps
from stores.models import StoreItem
from records.models import ItemRecord
from django.utils import timezone
import math
from datetime import datetime, time

MenuPricingParam = apps.get_model("pricing", "MenuPricingParam")


def sigmoid(x):
    if x < -30:
        return 0.0
    if x > 30:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def create_item_record(store_item, sold=1, is_dummy_flag=False):
    now = timezone.now()
    ItemRecord.objects.create(
        store_item_id=store_item.item_id,
        record_reservation_time=store_item.item_reservation_time,
        time_offset_idx=calculate_time_offset_idx(store_item, now),
        record_stock=store_item.item_stock,
        record_item_price=store_item.menu.menu_price,
        record_discount_rate=store_item.current_discount_rate,
        created_at=now,
        is_dummy=is_dummy_flag,
        sold=sold,  # sold 정보 명시적으로 저장 (DB 필드 존재해야 함)
        is_learned=False,  # 신규 생성 시 학습 미완료 상태로 기본 설정
    )


from django.db import transaction, IntegrityError


def safe_create_item_record(item, sold, is_dummy_flag):
    time_offset = calculate_time_offset_idx(item, timezone.now())
    try:
        with transaction.atomic():
            if not ItemRecord.objects.filter(
                store_item_id=item.item_id,
                record_reservation_time=item.item_reservation_time,
                time_offset_idx=time_offset,
                sold=sold,
                is_dummy=is_dummy_flag,
            ).exists():
                create_item_record(item, sold=sold, is_dummy_flag=is_dummy_flag)
    except IntegrityError:
        # 중복 삽입 시 무시(로깅 가능)
        pass


def calculate_time_offset_idx(store_item, current_time):
    # current_time을 한국 시간(KST) 기준으로 변환 후 naive datetime으로 만듦
    current_naive = timezone.localtime(current_time).replace(tzinfo=None)

    # DB 저장된 정수 시(hour)로 naive datetime 생성 (분, 초는 0)
    reservation_datetime = datetime.combine(
        store_item.item_reservation_date,
        time(hour=store_item.item_reservation_time, minute=0, second=0),
    )

    diff_minutes = (reservation_datetime - current_naive).total_seconds() / 60

    if diff_minutes <= 0:
        idx = 0
    else:
        idx = int((diff_minutes - 1) // 10) + 1

    return max(0, idx)
