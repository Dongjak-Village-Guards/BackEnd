from datetime import datetime
import math
from django.core.management.base import BaseCommand
from stores.models import StoreMenu, StoreItem
from records.models import ItemRecord
from pricing.models import MenuPricingParam, GlobalPricingParam
from pricing.utils import sigmoid


class Command(BaseCommand):
    help = "메뉴별 동적 할인율 파라미터 학습 (전역 파라미터 사용)"

    lr = 0.002
    epochs = 5

    def handle(self, *args, **kwargs):
        self.stdout.write("할인율 파라미터 학습 시작...")

        # GlobalPricingParam 오브젝트 하나만 가져오기 (없으면 생성)
        global_param, _ = GlobalPricingParam.objects.get_or_create(id=1)
        self.stdout.write(
            f"전역 파라미터 - beta0: {global_param.beta0}, alpha: {global_param.alpha}, gamma_tilde: {global_param.gamma_tilde}"
        )

        menus = StoreMenu.objects.all()
        if not menus:
            self.stdout.write("StoreMenu 데이터가 없습니다.")
            return

        a = global_param.beta0
        b = global_param.alpha

        gamma_db_val = global_param.gamma_tilde
        if gamma_db_val is None or not (-10.0 < gamma_db_val < 10.0):
            gamma = -1.0  # 기본값으로 초기화
        else:
            gamma = gamma_db_val

        # 메뉴별 가중치 업데이트는 계속 개별로 하되 학습 파라미터는 전역 a,b,gamma만 업데이트

        # 전체 메뉴별 아이템 아이디 수집 (모든 메뉴 합침)
        all_item_ids = []
        for menu in menus:
            all_item_ids.extend(menu.storeitem_set.values_list("item_id", flat=True))
        # 중복 제거
        all_item_ids = list(set(all_item_ids))
        self.stdout.write(f"전체 아이템 수 (중복 제거 후): {len(all_item_ids)}")

        # 학습 데이터 쿼리: 모든 메뉴 아이템 레코드 필터링 → 조건 제거
        queryset = ItemRecord.objects.filter(store_item_id__in=all_item_ids)

        record_count = queryset.count()
        if record_count == 0:
            self.stdout.write("ItemRecord 데이터가 없습니다.")
            return

        self.stdout.write(f"전체 학습 대상 레코드 수: {record_count}")

        # 최신 5000개 데이터만 사용
        records = queryset.order_by("-created_at")[:5000]

        store_items = StoreItem.objects.filter(
            item_id__in=[r.store_item_id for r in records]
        )
        store_item_map = {item.item_id: item for item in store_items}

        # 메뉴별 dp_weight 변동 사항 저장용 딕셔너리 추가
        menu_weight_updates = {}

        for _ in range(self.epochs):
            for r in records:
                store_item = store_item_map.get(r.store_item_id)
                if not store_item:
                    continue

                sold = r.sold
                w = store_item.menu.dp_weight
                t = r.time_offset_idx

                price = r.record_item_price * (1 - r.record_discount_rate)
                cost = store_item.menu.menu_price * 0.6  # 원가 60% 고정

                # 원가 반영 할인율 학습 변수 (가격에서 원가 차이)
                p_n = (price - cost) / 1000.0

                # 시간 인덱스 스케일링 (예: 10으로 나눠서 감쇠)
                t_scaled = t / 10.0

                z = a + b * p_n + gamma * t_scaled + w
                p = sigmoid(z)

                weight = 2.0 if sold == 1 else 1.0
                delta = (p - sold) * weight

                a -= self.lr * delta
                b -= self.lr * delta * p_n
                gamma -= self.lr * delta * t_scaled

                w -= self.lr * delta

                menu_id = store_item.menu.menu_id
                menu_weight_updates[menu_id] = w

        # 학습된 전역 파라미터 저장
        global_param.beta0 = a
        global_param.alpha = b
        global_param.gamma_tilde = gamma  # 감마 값을 그대로 저장
        global_param.save()

        # 업데이트된 메뉴별 dp_weight 저장
        for menu in menus:
            if menu.menu_id in menu_weight_updates:
                new_w = menu_weight_updates[menu.menu_id]
                menu.dp_weight = new_w
                menu.save(update_fields=["dp_weight", "updated_at"])
                self.stdout.write(
                    f"[메뉴: {menu.menu_name}] dp_weight 업데이트: {new_w:.6f}"
                )

        # # 학습 완료된 레코드 is_learned=True 처리
        # record_ids = [r.record_id for r in records]
        # ItemRecord.objects.filter(record_id__in=record_ids).update(is_learned=True)

        self.stdout.write(
            f"학습 완료 - beta0(a): {a:.4f}, alpha(b): {b:.4f}, gamma_tilde: {global_param.gamma_tilde:.4f}"
        )

        self.stdout.write("할인율 파라미터 학습 종료.")
