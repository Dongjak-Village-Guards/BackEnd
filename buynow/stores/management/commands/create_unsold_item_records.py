from django.core.management.base import BaseCommand
from stores.models import StoreItem
from pricing.utils import create_item_record
from django.utils import timezone
from datetime import datetime, time


class Command(BaseCommand):
    help = "미판매된 아이템에 대해 ItemRecord 생성"

    def handle(self, *args, **kwargs):
        now = timezone.now()
        unsold_items = StoreItem.objects.filter(
            item_reservation_date__lt=now.date()
        ) | StoreItem.objects.filter(
            item_reservation_date=now.date(), item_reservation_time__lt=now.time()
        )
        unsold_items = unsold_items.filter(item_stock=1)

        count = 0
        for item in unsold_items:
            exists = item_exists = False
            exists = create_item_record(item, sold=0, is_dummy_flag=False)
            count += 1

        self.stdout.write(self.style.SUCCESS(f"미판매 ItemRecord {count}건 생성 완료"))
