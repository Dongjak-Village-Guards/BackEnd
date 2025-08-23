from datetime import datetime
import math
from django.core.management.base import BaseCommand
from stores.models import StoreMenu, StoreItem
from records.models import ItemRecord
from pricing.models import MenuPricingParam
from pricing.utils import sigmoid


class Command(BaseCommand):
    help = "메뉴별 동적 할인율 파라미터 학습"

    lr = 0.002
    epochs = 5

    def gamma_to_gamma_tilde(self, gamma):
        val = math.exp(-gamma) - 1
        if val <= 0:
            val = 1e-8
        return math.log(val)

    def handle(self, *args, **kwargs):
        self.stdout.write("할인율 파라미터 학습 시작...")
        menus = StoreMenu.objects.all()
        if not menus:
            self.stdout.write("StoreMenu 데이터가 없습니다.")
            return

        for menu in menus:
            self.stdout.write(f"메뉴 [{menu.menu_name}] 학습 시작")
            param, _ = MenuPricingParam.objects.get_or_create(menu=menu)

            a = param.beta0
            b = param.alpha

            # 기존 gamma_tilde → gamma 역변환 (gamma_tilde가 없으면 기본값 -1.0)
            if param.gamma_tilde is not None:
                gamma = -math.log(math.exp(param.gamma_tilde) + 1)
            else:
                gamma = -1.0

            w = menu.dp_weight

            item_ids = menu.storeitem_set.values_list("item_id", flat=True)

            queryset = ItemRecord.objects.filter(
                store_item_id__in=item_ids, is_learned=False
            )

            record_count = queryset.count()
            if record_count == 0:
                self.stdout.write(f"{menu.menu_name}: 신규 학습 데이터 없음, 건너뜀")
                continue
            elif record_count < 10:
                self.stdout.write(
                    f"{menu.menu_name}: 학습 데이터 부족 (신규 {record_count}건)"
                )

            # 최신 100개 데이터만 학습 데이터로 사용
            records = queryset.order_by("-created_at")[:100]

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
                    w = store_item.menu.dp_weight  # 현재 StoreMenu dp_weight 재사용
                    t = r.time_offset_idx  # 과거 기록의 시간 인덱스 그대로 사용

                    price = r.record_item_price * (1 - r.record_discount_rate)
                    p_n = price / 1000.0

                    z = a + b * p_n + gamma * t + w
                    p = sigmoid(z)

                    # 여기서 sold가 1(팔림)이면 가중치 2.0, 아니면 1.0  <- 이 아래 2줄 살리고 그 아래 줄을 주석처리하던가...
                    weight = 2.0 if sold == 1 else 1.0
                    delta = (p - sold) * weight
                    # delta = p - sold

                    # 파라미터 경사 하강법 업데이트
                    a -= self.lr * delta
                    b -= self.lr * delta * p_n
                    gamma -= self.lr * delta * t
                    w -= self.lr * delta

            # 파라미터 저장
            param.beta0 = a
            param.alpha = b
            param.gamma_tilde = self.gamma_to_gamma_tilde(gamma)
            param.save()

            # 메뉴 가중치 업데이트
            menu.dp_weight = w
            menu.save(update_fields=["dp_weight", "updated_at"])

            # 학습 완료된 레코드 is_learned=True 처리
            record_ids = [r.record_id for r in records]
            ItemRecord.objects.filter(record_id__in=record_ids).update(is_learned=True)

            self.stdout.write(
                f"{menu.menu_name} 학습 완료 - beta0(a): {a:.4f}, alpha(b): {b:.4f}, gamma_tilde: {param.gamma_tilde:.4f}, dp_weight(w): {w:.4f}"
            )

        self.stdout.write("할인율 파라미터 학습 종료.")
