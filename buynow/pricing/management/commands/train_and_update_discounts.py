from datetime import datetime
import math
from django.core.management.base import BaseCommand
from stores.models import StoreMenu, StoreItem
from records.models import ItemRecord
from pricing.models import MenuPricingParam
from pricing.utils import sigmoid


class Command(BaseCommand):
    help = "메뉴별 동적 할인율 학습 및 StoreItem 할인율 업데이트"

    lr = 0.02
    epochs = 10
    price_grid_interval = 100

    def gamma_to_gamma_tilde(self, gamma):
        val = math.exp(-gamma) - 1
        if val <= 0:
            val = 1e-8
        return math.log(val)

    def handle(self, *args, **kwargs):
        self.stdout.write("할인율 학습 시작...")
        menus = StoreMenu.objects.all()
        if not menus:
            self.stdout.write("StoreMenu 데이터가 없습니다.")
            return

        for menu in menus:
            self.stdout.write(f"메뉴 [{menu.menu_name}] 학습 시작")
            param, _ = MenuPricingParam.objects.get_or_create(menu=menu)
            a = param.beta0
            b = param.alpha
            gamma = param.gamma
            w = menu.dp_weight  # 메뉴 가중치

            item_ids = menu.storeitem_set.values_list("item_id", flat=True)

            queryset = ItemRecord.objects.filter(
                store_item_id__in=item_ids, is_learned=False
            )

            if not queryset.exists():
                self.stdout.write(f"{menu.menu_name}: 신규 학습 데이터 없음, 건너뜀")
                continue

            record_count = queryset[:10].count()
            if record_count < 10:
                self.stdout.write(
                    f"{menu.menu_name}: 학습 데이터 부족 (신규 {record_count}건)"
                )

            # 실제 학습용 데이터 쿼리 (최대 10개)
            records = queryset.order_by("-created_at")[:10]

            store_items = StoreItem.objects.filter(
                item_id__in=[r.store_item_id for r in records]
            )
            store_item_map = {item.item_id: item for item in store_items}

            for _ in range(self.epochs):
                for r in records:
                    store_item = store_item_map.get(r.store_item_id)
                    if not store_item:
                        continue

                    sold = r.sold
                    w = store_item.menu.dp_weight
                    t = r.time_offset_idx

                    price = r.record_item_price * (1 - r.record_discount_rate)
                    p_n = price / 1000.0

                    z = a + b * p_n + gamma * t + w
                    p = sigmoid(z)

                    delta = p - sold

                    a -= self.lr * delta
                    b -= self.lr * delta * p_n
                    gamma -= self.lr * delta * t
                    w -= self.lr * delta  # 메뉴 가중치 업데이트

            param.beta0 = a
            param.alpha = b
            param.gamma_tilde = self.gamma_to_gamma_tilde(gamma)
            param.save()

            menu.dp_weight = w
            menu.save(update_fields=["dp_weight"])
            # [수정] 학습 후 해당 레코드들을 is_learned=True로 업데이트
            record_ids = [r.record_id for r in records]
            ItemRecord.objects.filter(record_id__in=record_ids).update(is_learned=True)

            max_discount = menu.storeitem_set.first().max_discount_rate or 0.3
            p_min = int(menu.menu_price * (1 - max_discount))
            p_max = menu.menu_price
            best_price = None
            best_profit = float("-inf")
            cost = menu.menu_cost_price

            for price_candidate in range(p_min, p_max + 1, self.price_grid_interval):
                p_n = price_candidate / 1000.0
                z = a + b * p_n + 0 + 0  # t, w 평균값 0 가정
                p = sigmoid(z)
                profit = p * price_candidate - cost
                if profit > best_profit:
                    best_profit = profit
                    best_price = price_candidate

            discount = max(0.0, min(1 - best_price / menu.menu_price, max_discount))
            today = datetime.today().date()
            # menu.storeitem_set.filter(item_stock=1).update(
            #     current_discount_rate=discount
            # )
            menu.storeitem_set.filter(item_stock=1, item_reservation_date=today).update(
                current_discount_rate=discount
            )

            self.stdout.write(
                f"{menu.menu_name}: 최적 가격 {best_price}원, 할인율 {discount:.4f}"
            )

        self.stdout.write("할인율 학습 및 업데이트 완료.")


# import math
# from django.core.management.base import BaseCommand
# from stores.models import StoreMenu, StoreItem
# from records.models import ItemRecord
# from pricing.models import MenuPricingParam
# from pricing.utils import sigmoid, update_discount_param


# class Command(BaseCommand):
#     help = "메뉴별 동적 할인율 학습 및 StoreItem 할인율 업데이트"

#     lr = 0.02
#     epochs = 10
#     price_grid_interval = 100

#     def handle(self, *args, **kwargs):
#         for menu in StoreMenu.objects.all():
#             param, _ = MenuPricingParam.objects.get_or_create(menu=menu)
#             a = param.beta0
#             b = param.alpha
#             gamma = param.gamma  # 감마 가중치

#             item_ids = menu.storeitem_set.values_list("item_id", flat=True)
#             # 미판매 포함, sold 컬럼 값에 따라서 학습 적용
#             records = ItemRecord.objects.filter(store_item_id__in=item_ids).order_by(
#                 "-created_at"
#             )[:100]
#             if not records.exists():
#                 self.stdout.write(f"{menu.menu_name}: 학습 데이터 부족, 건너뜀")
#                 continue

#             for _ in range(self.epochs):
#                 for r in records:
#                     store_item = StoreItem.objects.filter(
#                         item_id=r.store_item_id
#                     ).first()
#                     if not store_item:
#                         continue

#                     sold = (
#                         1 if r.record_stock == 0 else 1
#                     )  # sold 정보가 필요하면 정확히 식별하도록 수정

#                     w = store_item.menu.dp_weight  # 메뉴 가중치
#                     t = r.time_offset_idx  # 감마 반영용 시간 변수

#                     price = r.record_item_price * (1 - r.record_discount_rate)
#                     p_n = price / 1000.0

#                     z = a + b * p_n + gamma * t + w
#                     p = sigmoid(z)

#                     delta = p - sold

#                     a -= self.lr * delta
#                     b -= self.lr * delta * p_n
#                     gamma -= self.lr * delta * t
#                     # 메뉴 가중치 학습 코드 미포함, 필요시 별도 구현

#             # 학습 결과 저장
#             param.beta0 = a
#             param.alpha = b
#             param.gamma = gamma
#             param.save()

#             max_discount = menu.storeitem_set.first().max_discount_rate or 0.3
#             p_min = int(menu.menu_price * (1 - max_discount))
#             p_max = menu.menu_price
#             best_price = None
#             best_profit = float("-inf")
#             cost = menu.menu_cost_price

#             for price_candidate in range(p_min, p_max + 1, self.price_grid_interval):
#                 p_n = price_candidate / 1000.0
#                 # 할인 최적화 시에도 감마와 가중치 포함할 수 있도록 확장 가능
#                 # 여기서는 시간 t, 가중치 w를 평균값 등으로 가정하고 0으로 둠
#                 z = a + b * p_n + 0 + 0
#                 p = sigmoid(z)
#                 profit = p * price_candidate - cost
#                 if profit > best_profit:
#                     best_profit = profit
#                     best_price = price_candidate

#             discount = max(0.0, min(1 - best_price / menu.menu_price, max_discount))

#             menu.storeitem_set.filter(item_stock=1).update(
#                 current_discount_rate=discount
#             )
#             self.stdout.write(
#                 f"{menu.menu_name}: 최적 가격 {best_price}원, 할인율 {discount:.4f}"
#             )


# import math
# from django.core.management.base import BaseCommand
# from stores.models import StoreMenu, StoreItem
# from records.models import ItemRecord
# from pricing.models import MenuPricingParam


# class Command(BaseCommand):
#     help = "메뉴별 동적 할인율 학습 및 StoreItem 할인율 업데이트"

#     lr = 0.02
#     epochs = 10
#     price_grid_interval = 100

#     def sigmoid(self, x):
#         if x < -30:
#             return 0.0
#         if x > 30:
#             return 1.0
#         return 1.0 / (1.0 + math.exp(-x))

#     def handle(self, *args, **kwargs):
#         for menu in StoreMenu.objects.all():
#             param, _ = MenuPricingParam.objects.get_or_create(menu=menu)
#             a = param.beta0
#             b = param.alpha
#             gamma = param.gamma

#             item_ids = menu.storeitem_set.values_list("item_id", flat=True)
#             records = ItemRecord.objects.filter(store_item_id__in=item_ids).order_by(
#                 "-created_at"
#             )[:1000]
#             if not records.exists():
#                 self.stdout.write(f"{menu.menu_name}: 학습 데이터 부족, 건너뜀")
#                 continue

#             for _ in range(self.epochs):
#                 for r in records:
#                     price = r.record_item_price * (1 - r.record_discount_rate)
#                     p_n = price / 1000.0
#                     y = 1  # 모두 팔린 상태의 ItemRecord
#                     z = a + b * p_n
#                     p = self.sigmoid(z)
#                     delta = p - y
#                     a -= self.lr * delta
#                     b -= self.lr * delta * p_n

#             param.beta0 = a
#             param.alpha = b
#             param.save()

#             max_discount = menu.storeitem_set.first().max_discount_rate or 0.3
#             p_min = int(menu.menu_price * (1 - max_discount))
#             p_max = menu.menu_price

#             best_price = None
#             best_profit = float("-inf")
#             cost = menu.menu_cost_price

#             for price_candidate in range(p_min, p_max + 1, self.price_grid_interval):
#                 p_n = price_candidate / 1000.0
#                 z = a + b * p_n
#                 p = self.sigmoid(z)
#                 profit = p * price_candidate - cost
#                 if profit > best_profit:
#                     best_profit = profit
#                     best_price = price_candidate

#             discount = max(0.0, min(1 - best_price / menu.menu_price, max_discount))

#             menu.storeitem_set.filter(item_stock=1).update(
#                 current_discount_rate=discount
#             )
#             self.stdout.write(
#                 f"{menu.menu_name}: 최적 가격 {best_price}원, 할인율 {discount:.4f}"
#             )
