from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from stores.models import StoreItem
from records.models import ItemRecord
from pricing.utils import safe_create_item_record
from django.core.management import call_command


class Command(BaseCommand):
    help = "어제 미판매(재고 0) 아이템에 대해 배치 단위로 ItemRecord 생성 후 할인율 학습 수행"

    batch_size = 100

    def handle(self, *args, **kwargs):
        self.stdout.write("어제 미판매(재고 0) 아이템 배치별 레코드 생성 시작...")

        yesterday = timezone.localtime().date() - timedelta(
            days=1
        )  # 한국 시간 기준 어제

        candidate_qs = StoreItem.objects.filter(
            item_reservation_date=yesterday,
            item_stock=0,
        )

        total_count = candidate_qs.count()
        self.stdout.write(f"처리 대상 아이템 총 {total_count}건")

        created_count = 0
        start = 0

        while start < total_count:
            batch_items = candidate_qs[start : start + self.batch_size]

            for item in batch_items:
                exists = ItemRecord.objects.filter(
                    store_item_id=item.item_id,
                    sold=0,
                ).exists()
                if not exists:
                    safe_create_item_record(
                        item,
                        sold=0,
                        is_dummy_flag=False,
                    )
                    created_count += 1

            self.stdout.write(
                f"{min(start + self.batch_size, total_count)}건 처리 완료..."
            )
            start += self.batch_size

        self.stdout.write(f"생성된 신규 ItemRecord 총 {created_count}건")

        self.stdout.write("할인율 학습 시작...")
        call_command("train_records")
        self.stdout.write("어제의 미판매 건에 대한 업데이트 및 학습 완료.")
