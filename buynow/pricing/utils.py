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
    )


def update_discount_param(store_item, sold=1):
    param, _ = MenuPricingParam.objects.get_or_create(menu=store_item.menu)

    a = param.beta0
    b = param.alpha
    gamma = param.gamma  # 감마 파라미터
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
    param.gamma = gamma
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


# from pricing.models import MenuPricingParam
# from stores.models import StoreItem, StoreMenu
# from records.models import ItemRecord
# import numpy as np
# from django.utils import timezone
# import math
# from datetime import datetime, time


# def sigmoid(x):
#     if x < -30:
#         return 0.0
#     if x > 30:
#         return 1.0
#     return 1.0 / (1.0 + math.exp(-x))


# def create_item_record(store_item, sold=1, is_dummy_flag=False):
#     now = timezone.now()
#     ItemRecord.objects.create(
#         store_item_id=store_item.item_id,
#         record_reservation_time=store_item.item_reservation_time,
#         time_offset_idx=calculate_time_offset_idx(store_item, now),
#         record_stock=store_item.item_stock,
#         record_item_price=store_item.menu.menu_price,
#         record_discount_rate=store_item.current_discount_rate,
#         created_at=now,
#         is_dummy=is_dummy_flag,
#     )


# def update_discount_param(store_item, sold=1):
#     param, _ = MenuPricingParam.objects.get_or_create(menu=store_item.menu)

#     a = param.beta0
#     b = param.alpha
#     w = store_item.menu.dp_weight  # 메뉴 가중치
#     lr = 1e-3

#     price = store_item.menu.menu_price * (1 - store_item.current_discount_rate)
#     p_n = price / 1000.0

#     z = a + b * p_n + w
#     p = sigmoid(z)
#     grad = sold - p

#     a += lr * grad
#     b += lr * grad * p_n
#     new_w = w + lr * grad

#     store_item.menu.dp_weight = new_w
#     store_item.menu.save(update_fields=["dp_weight"])

#     param.beta0 = a
#     param.alpha = b
#     param.save()


# def calculate_time_offset_idx(store_item, current_time):
#     reservation_datetime = datetime.combine(
#         store_item.item_reservation_date, time(store_item.item_reservation_time)
#     )

#     if reservation_datetime.tzinfo is None:
#         reservation_datetime = timezone.make_aware(
#             reservation_datetime, timezone=current_time.tzinfo
#         )

#     diff_minutes = (reservation_datetime - current_time).total_seconds() / 60
#     idx = int(max(0, min(18, diff_minutes // 10)))
#     return idx


# from pricing.models import MenuPricingParam
# from stores.models import StoreItem, StoreMenu
# from records.models import ItemRecord
# import numpy as np
# from django.utils import timezone
# import math
# from datetime import datetime, time


# def sigmoid(x):
#     if x < -30:
#         return 0.0
#     if x > 30:
#         return 1.0
#     return 1.0 / (1.0 + math.exp(-x))


# def create_item_record(store_item, sold=1, is_dummy_flag=False):
#     from django.utils import timezone

#     now = timezone.now()
#     ItemRecord.objects.create(
#         store_item_id=store_item.item_id,
#         record_reservation_time=store_item.item_reservation_time,
#         time_offset_idx=calculate_time_offset_idx(store_item, now),
#         record_stock=store_item.item_stock,
#         record_item_price=store_item.menu.menu_price,
#         record_discount_rate=store_item.current_discount_rate,
#         created_at=now,
#         is_dummy=is_dummy_flag,
#     )


# def update_discount_param(store_item, sold=1):
#     param, _ = MenuPricingParam.objects.get_or_create(menu=store_item.menu)

#     a = param.beta0
#     b = param.alpha
#     w = store_item.menu.dp_weight  # 메뉴 가중치
#     lr = 1e-3

#     price = store_item.menu.menu_price * (1 - store_item.current_discount_rate)
#     p_n = price / 1000.0

#     z = a + b * p_n + w
#     p = sigmoid(z)
#     grad = sold - p

#     a += lr * grad
#     b += lr * grad * p_n
#     new_w = w + lr * grad

#     store_item.menu.dp_weight = new_w
#     store_item.menu.save(update_fields=['dp_weight'])

#     param.beta0 = a
#     param.alpha = b
#     param.save()


#     param, _ = MenuPricingParam.objects.get_or_create(menu=store_item.menu)

#     # 기존 파라미터
#     a = param.beta0
#     b = param.alpha
#     w = store_item.menu.dp_weight  # 메뉴 가중치 필드
#     lr = 1e-3

#     price = store_item.menu.menu_price * (1 - store_item.current_discount_rate)
#     p_n = price / 1000.0

#     # 예: z = a + b*p_n + d1*w (d1 == 1.0 고정 또는 또 다른 파라미터로 확장 가능)
#     z = a + b * p_n + w  # 혹은 w에 별도 계수를 곱해도 됨
#     p = sigmoid(z)
#     grad = sold - p

#     # 파라미터 업데이트
#     a += lr * grad
#     b += lr * grad * p_n
#     # 메뉴 가중치 업데이트 예 (가중치 없으면 이 부분 제외)
#     new_w = w + lr * grad
#     store_item.menu.dp_weight = new_w
#     store_item.menu.save(update_fields=["dp_weight"])

#     param.beta0 = a
#     param.alpha = b
#     param.save()

#     p_min = int(store_item.menu.menu_price * (1 - store_item.max_discount_rate))
#     p_max = store_item.menu.menu_price

#     best_price = None
#     best_profit = float("-inf")

#     for price_candidate in range(p_min, p_max + 1, 100):
#         p_n = price_candidate / 1000.0
#         eta = a + b * p_n
#         p = sigmoid(eta)
#         profit = p * price_candidate - store_item.menu.menu_cost_price
#         if profit > best_profit:
#             best_profit = profit
#             best_price = price_candidate

#     discount_new = max(
#         0.0,
#         min(1 - best_price / store_item.menu.menu_price, store_item.max_discount_rate),
#     )
#     store_item.current_discount_rate = discount_new
#     store_item.save(update_fields=["current_discount_rate"])


# def calculate_time_offset_idx(store_item, current_time):
#     # naive datetime 생성
#     reservation_datetime = datetime.combine(
#         store_item.item_reservation_date, time(store_item.item_reservation_time)
#     )

#     # naive -> aware 변환 (current_time의 tzinfo 사용)
#     if reservation_datetime.tzinfo is None:
#         reservation_datetime = timezone.make_aware(
#             reservation_datetime, timezone=current_time.tzinfo
#         )

#     diff_minutes = (reservation_datetime - current_time).total_seconds() / 60
#     idx = int(max(0, min(18, diff_minutes // 10)))
#     return idx
