from datetime import datetime
import math
from django.core.management.base import BaseCommand
from django.utils import timezone as dj_timezone
from stores.models import StoreMenu
from pricing.models import MenuPricingParam
from pricing.utils import sigmoid, calculate_time_offset_idx


class Command(BaseCommand):
    help = "StoreItem별 현재 할인율 시간별로 업데이트 (학습된 파라미터 활용 및 할인율 보정)"

    price_grid_interval = 10  # 가격 탐색 간격 10원으로 세밀화

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
        max_time_offset = 18  # 3시간 이내 (10분단위 인덱스 최대치)
        batch_size = 1000  # 메모리/부하 완화용 배치 크기

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

            queryset = menu.storeitem_set.filter(
                item_stock=1, item_reservation_date=today
            )

            items_to_update = []
            time_offset_map = {}

            for store_item in queryset.iterator(chunk_size=batch_size):
                t = calculate_time_offset_idx(store_item, now)
                if t is not None and t <= max_time_offset:
                    items_to_update.append(store_item)
                    time_offset_map[store_item.item_id] = t

            for store_item in items_to_update:
                t = time_offset_map[store_item.item_id]
                # self.stdout.write(
                #     f"item_id={store_item.item_id}, time_offset_idx={t}"
                # )  # 시간 인덱스 로그 출력
                cost = menu.menu_cost_price

                max_discount = store_item.max_discount_rate or 0.3
                p_min = int(menu.menu_price * (1 - max_discount))
                p_max = menu.menu_price

                best_price = None
                best_profit = float("-inf")

                p_min_n = p_min / 1000.0
                p_max_n = p_max / 1000.0

                # z_min, z_max로 예상 구매 확률 계산
                z_min = a + b * p_min_n + gamma * t + w
                z_max = a + b * p_max_n + gamma * t + w

                p_min_prob = sigmoid(z_min)
                p_max_prob = sigmoid(z_max)

                expected_max_discount = 1 - p_min / menu.menu_price
                expected_min_discount = 1 - p_max / menu.menu_price

                # 구매 확률 기반 할인율 보정 (숫자는 조정 가능...)
                if p_min_prob < 0.2:
                    expected_max_discount = min(expected_max_discount, 0.3)
                if p_max_prob > 0.8:
                    expected_min_discount = max(expected_min_discount, 0.05)

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

                if discount < expected_min_discount:
                    discount = expected_min_discount
                elif discount > expected_max_discount:
                    discount = expected_max_discount

                previous_discount = store_item.current_discount_rate

                store_item.current_discount_rate = discount
                store_item.save(update_fields=["current_discount_rate", "updated_at"])

                if previous_discount != discount:
                    self.stdout.write(
                        f"menu_id={menu.menu_id} item_id={store_item.item_id}: 할인율 변경 - 이전: {previous_discount:.4f}, 현재: {discount:.4f}, 시간인덱스={t}, 최적가격={best_price}"
                    )
                else:
                    self.stdout.write(
                        f"menu_id={menu.menu_id} item_id={store_item.item_id}: 할인율 변동 없음 - {discount:.4f}, 시간인덱스={t}, 최적가격={best_price}"
                    )

                self.stdout.write(
                    f"item_id={store_item.item_id}, time_offset_idx={t}, 최적가격={best_price}, 할인율={discount:.4f}"
                )

        self.stdout.write("할인율 시간별 업데이트 완료.")
