from datetime import datetime, timedelta
import math
from django.core.management.base import BaseCommand
from django.utils import timezone as dj_timezone
from stores.models import StoreMenu
from pricing.models import GlobalPricingParam
from pricing.utils import sigmoid, calculate_time_offset_idx


class Command(BaseCommand):
    help = "StoreItem별 현재 할인율 시간별로 업데이트 (전역 파라미터 사용)"

    price_grid_interval = 10  # 가격 탐색 간격 10원으로 세밀화

    def gamma_tilde_to_gamma(self, gamma_tilde):
        clipped_val = max(gamma_tilde, -30)
        return -math.log1p(math.exp(clipped_val))  # log1p(x) = log(1+x)

    def handle(self, *args, **kwargs):
        self.stdout.write("할인율 시간별 업데이트 시작...")

        try:
            param = GlobalPricingParam.objects.get(id=1)
        except GlobalPricingParam.DoesNotExist:
            self.stdout.write("전역 파라미터가 없습니다. 종료합니다.")
            return

        now = dj_timezone.now()
        today = now.date()
        tomorrow = today + timedelta(days=1)
        max_time_offset = 143  # 하루 최대 시간 인덱스 (10분 단위)

        batch_size = 1000

        a, b = param.beta0, param.alpha
        gamma = self.gamma_tilde_to_gamma(param.gamma_tilde)

        menus = StoreMenu.objects.all()
        if not menus:
            self.stdout.write("StoreMenu 데이터가 없습니다.")
            return

        for menu in menus:
            self.stdout.write(f"메뉴 [{menu.menu_name}] 할인율 계산 시작")

            w = menu.dp_weight  # 메뉴별 가중치 유지

            queryset = menu.storeitem_set.filter(
                item_stock=1, item_reservation_date__range=(today, tomorrow)
            )

            items_to_update = []
            time_offset_map = {}

            for store_item in queryset.iterator(chunk_size=batch_size):
                t = calculate_time_offset_idx(store_item, now)
                if t is not None and t <= max_time_offset:
                    items_to_update.append(store_item)
                    time_offset_map[store_item.item_id] = t
                    self.stdout.write(
                        f"DEBUG: item_id={store_item.item_id}, time_offset_idx={t}"
                    )

            # 중복 검사 유지
            seen_item_ids = set()
            duplicates_found = False
            for store_item in items_to_update:
                if store_item.item_id in seen_item_ids:
                    duplicates_found = True
                    self.stdout.write(f"중복 발견: item_id={store_item.item_id}")
                else:
                    seen_item_ids.add(store_item.item_id)
            if not duplicates_found:
                self.stdout.write("items_to_update 리스트에 중복 아이템 없음")

            # time_offset_map 확인
            for store_item in items_to_update:
                t = time_offset_map.get(store_item.item_id, None)
                if t is None:
                    self.stdout.write(
                        f"time_offset_map에 item_id={store_item.item_id} 없음"
                    )
                else:
                    self.stdout.write(
                        f"item_id={store_item.item_id}, time_offset_idx={t}"
                    )

            for store_item in items_to_update:
                t = time_offset_map[store_item.item_id]
                t_scaled = t / 10.0  # 학습 코드와 동일한 시간 인덱스 스케일링

                cost = menu.menu_price * 0.7

                max_discount = store_item.max_discount_rate or 0.3
                p_min = int(menu.menu_price * (1 - max_discount))
                p_max = menu.menu_price

                best_price = None
                best_profit = float("-inf")

                expected_max_discount = 1 - p_min / menu.menu_price
                expected_min_discount = 1 - p_max / menu.menu_price

                for price_candidate in range(
                    p_min, p_max + 1, self.price_grid_interval
                ):
                    # p_n 계산에 원가 반영하여 학습과 일치
                    p_n = (price_candidate - cost) / 1000.0
                    z = a + b * p_n + gamma * t_scaled + w
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

        self.stdout.write("할인율 시간별 업데이트 완료.")
