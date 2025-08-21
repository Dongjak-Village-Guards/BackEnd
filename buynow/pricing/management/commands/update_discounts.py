from datetime import datetime, timezone, time
import math
from django.core.management.base import BaseCommand
from django.utils import timezone as dj_timezone
from stores.models import StoreMenu
from pricing.models import MenuPricingParam
from pricing.utils import sigmoid, calculate_time_offset_idx


class Command(BaseCommand):
    help = "StoreItem별 현재 할인율 시간별로 업데이트"

    price_grid_interval = 100

    def gamma_tilde_to_gamma(self, gamma_tilde):
        return -math.log(math.exp(gamma_tilde) + 1)

    def handle(self, *args, **kwargs):
        self.stdout.write("할인율 시간별 업데이트 시작...")
        menus = StoreMenu.objects.all()
        if not menus:
            self.stdout.write("StoreMenu 데이터가 없습니다.")
            return

        now = dj_timezone.now()
        today = now.date()

        # 3시간(180분) 이내만 처리 -> 10분 단위 인덱스로 18 이하
        max_time_offset = 18

        batch_size = 1000

        for menu in menus:
            self.stdout.write(f"메뉴 [{menu.menu_name}] 할인율 계산 시작")

            try:
                param = MenuPricingParam.objects.get(menu=menu)
            except MenuPricingParam.DoesNotExist:
                self.stdout.write(f"{menu.menu_name}: 파라미터가 없습니다. 건너뜀")
                continue

            a, b = param.beta0, param.alpha
            gamma = self.gamma_tilde_to_gamma(param.gamma_tilde)
            w = menu.dp_weight

            # 오늘 예약된 재고 있는 아이템 대상으로 필터
            queryset = menu.storeitem_set.filter(
                item_stock=1, item_reservation_date=today
            )

            items_to_update = []
            time_offset_map = {}

            # iterator(chunk_size=batch_size) 로 메모리 절약하며 반복 처리
            for store_item in queryset.iterator(chunk_size=batch_size):
                # 시간 인덱스 계산 함수 사용 (기존 함수 그대로 활용)
                idx = calculate_time_offset_idx(store_item, now)
                if idx is not None and idx <= max_time_offset:
                    items_to_update.append(store_item)
                    time_offset_map[store_item.item_id] = idx

            for store_item in items_to_update:
                t = time_offset_map[store_item.item_id]
                cost = menu.menu_cost_price

                max_discount = store_item.max_discount_rate or 0.3
                p_min = int(menu.menu_price * (1 - max_discount))
                p_max = menu.menu_price

                best_price = None
                best_profit = float("-inf")

                # 100원 간격 그리드 탐색
                for price_candidate in range(
                    p_min, p_max + 1, self.price_grid_interval
                ):
                    p_n = price_candidate / 1000.0
                    z = a + b * p_n + gamma * t + w
                    p = sigmoid(z)
                    profit = p * price_candidate - cost
                    if profit > best_profit:
                        best_profit = profit
                        best_price = price_candidate

                discount = max(0.0, min(1 - best_price / menu.menu_price, max_discount))

                store_item.current_discount_rate = discount
                store_item.save(update_fields=["current_discount_rate"])

                self.stdout.write(
                    f"{menu.menu_name} - item_id {store_item.item_id}: 최적 가격 {best_price}원, 할인율 {discount:.4f}"
                )

        self.stdout.write("할인율 시간별 업데이트 완료.")
