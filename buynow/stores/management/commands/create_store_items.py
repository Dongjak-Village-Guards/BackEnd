from datetime import date, timedelta
import random
from django.core.management.base import BaseCommand

from stores.models import StoreItem, StoreMenuSpace


class Command(BaseCommand):
    help = "StoreItem만 오늘부터 8일간 배치(20개)로 추가 생성"

    def handle(self, *args, **options):
        today = date(2025, 8, 21)
        days = 8
        hours = list(range(24))
        batch_size = 20

        def find_max_discount(menu):
            return round(random.uniform(0.15, 0.5), 2)

        records_to_create = []

        store_menu_spaces = StoreMenuSpace.objects.all()

        for sms in store_menu_spaces:
            menu = sms.menu
            max_discount_rate = find_max_discount(menu)

            for day_offset in range(days):
                date_to_create = today + timedelta(days=day_offset)
                for hour in hours:
                    stock = 1 if random.random() < 0.5 else 0
                    record = StoreItem(
                        menu=menu,
                        space=sms.space,
                        store=menu.store,
                        item_reservation_date=date_to_create,
                        item_reservation_day=date_to_create.strftime("%a"),
                        item_reservation_time=hour,
                        item_stock=stock,
                        current_discount_rate=0.1,
                        max_discount_rate=max_discount_rate,
                        is_dummy=True,
                    )
                    records_to_create.append(record)

                    if len(records_to_create) >= batch_size:
                        StoreItem.objects.bulk_create(records_to_create)
                        self.stdout.write(
                            self.style.NOTICE(
                                f"StoreItem 생성 진행: {len(records_to_create)}개 생성"
                            )
                        )
                        records_to_create.clear()

        # 남은 데이터가 있으면 한 번 더 생성
        if records_to_create:
            StoreItem.objects.bulk_create(records_to_create)
            self.stdout.write(
                self.style.NOTICE(
                    f"StoreItem 생성 완료, 마지막 배치: {len(records_to_create)}개"
                )
            )

        self.stdout.write(self.style.SUCCESS("✅ StoreItem 배치 생성 완료"))
