import math
from django.core.management.base import BaseCommand
from stores.models import StoreMenu, StoreItem
from records.models import ItemRecord
from pricing.models import MenuPricingParam


class Command(BaseCommand):
    help = "메뉴별 동적 할인율 학습 및 StoreItem 할인율 업데이트"

    lr = 0.02
    epochs = 10
    price_grid_interval = 100

    def sigmoid(self, x):
        if x < -30:
            return 0.0
        if x > 30:
            return 1.0
        return 1.0 / (1.0 + math.exp(-x))

    def handle(self, *args, **kwargs):
        for menu in StoreMenu.objects.all():
            param, _ = MenuPricingParam.objects.get_or_create(menu=menu)
            a = param.beta0
            b = param.alpha
            gamma = param.gamma

            item_ids = menu.storeitem_set.values_list("item_id", flat=True)
            records = ItemRecord.objects.filter(store_item_id__in=item_ids).order_by(
                "-created_at"
            )[:1000]
            if not records.exists():
                self.stdout.write(f"{menu.menu_name}: 학습 데이터 부족, 건너뜀")
                continue

            for _ in range(self.epochs):
                for r in records:
                    price = r.record_item_price * (1 - r.record_discount_rate)
                    p_n = price / 1000.0
                    y = 1  # 모두 팔린 상태의 ItemRecord
                    z = a + b * p_n
                    p = self.sigmoid(z)
                    delta = p - y
                    a -= self.lr * delta
                    b -= self.lr * delta * p_n

            param.beta0 = a
            param.alpha = b
            param.save()

            max_discount = menu.storeitem_set.first().max_discount_rate or 0.3
            p_min = int(menu.menu_price * (1 - max_discount))
            p_max = menu.menu_price

            best_price = None
            best_profit = float("-inf")
            cost = menu.menu_cost_price

            for price_candidate in range(p_min, p_max + 1, self.price_grid_interval):
                p_n = price_candidate / 1000.0
                z = a + b * p_n
                p = self.sigmoid(z)
                profit = p * price_candidate - cost
                if profit > best_profit:
                    best_profit = profit
                    best_price = price_candidate

            discount = max(0.0, min(1 - best_price / menu.menu_price, max_discount))

            menu.storeitem_set.filter(item_stock=1).update(
                current_discount_rate=discount
            )
            self.stdout.write(
                f"{menu.menu_name}: 최적 가격 {best_price}원, 할인율 {discount:.4f}"
            )
