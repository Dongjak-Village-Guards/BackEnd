from pricing.models import MenuPricingParam
from stores.models import StoreItem
from records.models import ItemRecord
from django.utils import timezone
import math
from datetime import datetime, time


def sigmoid(x):
    if x < -30:
        return 0.0
    if x > 30:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def gamma_to_gamma_tilde(gamma):
    val = math.exp(-gamma) - 1
    if val <= 0:
        val = 1e-8
    return math.log(val)


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


# def safe_create_item_record(item, sold, is_dummy_flag):
#     time_offset = calculate_time_offset_idx(item, timezone.now())
#     exists = ItemRecord.objects.filter(
#         store_item_id=item.item_id,
#         record_reservation_time=item.item_reservation_time,
#         time_offset_idx=time_offset,
#         sold=sold,
#         is_dummy=is_dummy_flag,
#     ).exists()
#     if not exists:
#         create_item_record(item, sold=sold, is_dummy_flag=is_dummy_flag)

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


def update_discount_param(store_item, sold=1):
    param, _ = MenuPricingParam.objects.get_or_create(menu=store_item.menu)

    a = param.beta0
    b = param.alpha
    gamma = param.gamma  # 읽기 전용 프로퍼티로 gamma 값을 읽는다
    w = store_item.menu.dp_weight  # 메뉴 가중치 필드
    lr = 1e-3

    price = store_item.menu.menu_price * (1 - store_item.current_discount_rate)
    p_n = price / 1000.0

    # time_offset_idx 같은 시간 변수 필요하면 모델 인자로 받아 계산해 전달하거나 별도 로직 필요
    # 예시: 현재는 0으로 두었으나 호출부에서 't'를 넘기도록 확장 가능
    t = 0

    z = a + b * p_n + gamma * t + w
    p = sigmoid(z)
    grad = sold - p

    a += lr * grad
    b += lr * grad * p_n
    gamma += lr * grad * t
    new_w = w + lr * grad

    store_item.menu.dp_weight = new_w
    store_item.menu.save(update_fields=["dp_weight"])

    param.beta0 = a
    param.alpha = b
    param.gamma_tilde = gamma_to_gamma_tilde(gamma)  # 업데이트된 gamma로 변환
    param.save()


def calculate_time_offset_idx(store_item, current_time):
    reservation_datetime = datetime.combine(
        store_item.item_reservation_date, time(store_item.item_reservation_time)
    )

    if reservation_datetime.tzinfo is None:
        reservation_datetime = timezone.make_aware(
            reservation_datetime, timezone=current_time.tzinfo
        )

    diff_minutes = (reservation_datetime - current_time).total_seconds() / 60
    idx = int(max(0, min(18, diff_minutes // 10)))
    return idx
