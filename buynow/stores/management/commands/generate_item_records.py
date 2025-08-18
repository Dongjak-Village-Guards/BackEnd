# stores/management/commands/generate_item_records.py
from django.core.management.base import BaseCommand
from datetime import datetime, timedelta
from stores.models import StoreItem
from records.models import ItemRecord
from django.utils import timezone


class Command(BaseCommand):
    help = '10분마다 StoreItem -> ItemRecord 자동 생성'

    def handle(self, *args, **kwargs):
        now = timezone.localtime()
        records_to_create = []

        # item_stock=1인 아이템만 조회
        store_items = StoreItem.objects.filter(item_stock=1).select_related('menu')

        for store_item in store_items:
            reservation_datetime = timezone.make_aware(
                datetime.combine(store_item.item_reservation_date, datetime.min.time()) 
                + timedelta(hours=store_item.item_reservation_time),
                timezone.get_current_timezone()
            )

            if reservation_datetime <= now:
                continue  # 현재 시각 이전은 제외

            delta_minutes = (reservation_datetime - now).total_seconds() / 60
            time_offset_idx = max(0, min(18, int(delta_minutes // 10)))

            record = ItemRecord(
                store_item_id=store_item.item_id,
                record_reservation_time=store_item.item_reservation_time,
                time_offset_idx=time_offset_idx,
                record_stock=store_item.item_stock,
                record_item_price=store_item.menu.menu_price,
                record_discount_rate=store_item.current_discount_rate,
            )
            records_to_create.append(record) # 모아뒀다가 한번에 DB 업데이트

        if records_to_create:
            ItemRecord.objects.bulk_create(records_to_create, ignore_conflicts=True)

        self.stdout.write(self.style.SUCCESS('ItemRecords 생성 완료'))
