from pricing.models import MenuPricingParam
from stores.models import StoreItem, StoreMenu
from records.models import ItemRecord
import numpy as np
from django.utils import timezone
import math


def sigmoid(x):
    if x < -30:
        return 0.0
    if x > 30:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def record_event_and_update_discount(store_item, sold=1, is_dummy_flag=False):
    now = timezone.now()

    ItemRecord.objects.create(
        store_item_id=store_item.item_id,
        record_reservation_time=store_item.item_reservation_time,
        time_offset_idx=calculate_time_offset_idx(store_item, now),
        record_stock=store_item.item_stock,
        record_item_price=store_item.menu.menu_price,
        record_discount_rate=store_item.current_discount_rate,
        created_at=now,
        is_dummy=is_dummy_flag,  # 호출할 때 플래그로 결정
    )

    param, _ = MenuPricingParam.objects.get_or_create(menu=store_item.menu)

    # 기존 파라미터
    a = param.beta0
    b = param.alpha
    w = store_item.menu.dp_weight  # 메뉴 가중치 필드
    lr = 1e-3

    price = store_item.menu.menu_price * (1 - store_item.current_discount_rate)
    p_n = price / 1000.0

    # 예: z = a + b*p_n + d1*w (d1 == 1.0 고정 또는 또 다른 파라미터로 확장 가능)
    z = a + b * p_n + w  # 혹은 w에 별도 계수를 곱해도 됨
    p = sigmoid(z)
    grad = sold - p

    # 파라미터 업데이트
    a += lr * grad
    b += lr * grad * p_n
    # 메뉴 가중치 업데이트 예 (가중치 없으면 이 부분 제외)
    new_w = w + lr * grad
    store_item.menu.dp_weight = new_w
    store_item.menu.save(update_fields=["dp_weight"])

    param.beta0 = a
    param.alpha = b
    param.save()

    p_min = int(store_item.menu.menu_price * (1 - store_item.max_discount_rate))
    p_max = store_item.menu.menu_price

    best_price = None
    best_profit = float("-inf")

    for price_candidate in range(p_min, p_max + 1, 100):
        p_n = price_candidate / 1000.0
        eta = a + b * p_n
        p = sigmoid(eta)
        profit = p * price_candidate - store_item.menu.menu_cost_price
        if profit > best_profit:
            best_profit = profit
            best_price = price_candidate

    discount_new = max(
        0.0,
        min(1 - best_price / store_item.menu.menu_price, store_item.max_discount_rate),
    )
    store_item.current_discount_rate = discount_new
    store_item.save(update_fields=["current_discount_rate"])


def calculate_time_offset_idx(store_item, current_time):
    from datetime import datetime, time

    reservation_datetime = datetime.combine(
        store_item.item_reservation_date, time(store_item.item_reservation_time)
    )
    diff_minutes = (reservation_datetime - current_time).total_seconds() / 60
    idx = int(max(0, min(18, diff_minutes // 10)))
    return idx
