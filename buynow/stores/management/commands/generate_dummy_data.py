from django.core.management.base import BaseCommand, CommandError
import random
from datetime import datetime, timedelta
from faker import Faker
from accounts.models import User
from stores.models import (
    Store, StoreSpace, StoreMenu, StoreMenuSpace,
    StoreOperatingHour, StoreItem, StoreSlot
)
from reservations.models import Reservation, UserLike


class Command(BaseCommand):
    help = "전체 더미데이터 생성 (ItemRecord 제외) - 확률 높인 버전"

    def add_arguments(self, parser):
        parser.add_argument('--dev', action='store_true', help='개발 DB에 생성')
        parser.add_argument('--prod', action='store_true', help='운영 DB에 생성 (확인 필요)')
        parser.add_argument('--skip-delete', action='store_true', help='기존 데이터 삭제 없이 추가')
        parser.add_argument('--owners', type=int, default=10)
        parser.add_argument('--customers', type=int, default=10)
        parser.add_argument('--stores', type=int, default=10)
        parser.add_argument('--days', type=int, default=14)
        parser.add_argument('--hours', nargs='+', type=int, default=list(range(24)), help='시간 슬롯 목록 (기본 0~23)')

    def handle(self, *args, **options):
        if not options['dev'] and not options['prod']:
            raise CommandError("--dev 또는 --prod 옵션 중 하나를 지정하세요.")
        
        if options['prod']:
            self.stdout.write(self.style.WARNING("⚠ 운영 DB에서 실행됩니다."))
            confirm = input("정말 실행하시겠습니까? (YES 입력) : ")
            if confirm != "YES":
                self.stdout.write(self.style.ERROR("취소됨"))
                return

        faker = Faker()
        days = options['days']
        hours = options['hours']

        # --- 기존 데이터 삭제 ---
        if not options['skip_delete']:
            Reservation.objects.all().delete()
            UserLike.objects.all().delete()
            StoreOperatingHour.objects.all().delete()
            StoreItem.objects.all().delete()
            StoreSlot.objects.all().delete()
            StoreMenuSpace.objects.all().delete()
            StoreMenu.objects.all().delete()
            StoreSpace.objects.all().delete()
            Store.objects.all().delete()
            # User 중 admin은 남기고 싶으면 여기 조건 변경
            User.objects.exclude(user_role='admin').delete()

        # --- Users ---
        owners = [
            User.objects.create(
                user_email=faker.unique.email(),
                user_image_url=faker.image_url(),
                user_password=faker.password(),
                user_role='owner',
                user_address=faker.address(),
                user_discounted_cost_sum=0
            ) for _ in range(options['owners'])
        ]
        customers = [
            User.objects.create(
                user_email=faker.unique.email(),
                user_image_url=faker.image_url(),
                user_password=faker.password(),
                user_role='customer',
                user_address=faker.address(),
                user_discounted_cost_sum=0
            ) for _ in range(options['customers'])
        ]

        # --- Stores ---
        stores = []
        stores_per_owner = max(1, options['stores'] // len(owners))
        for owner in owners:
            for _ in range(stores_per_owner):
                store = Store.objects.create(
                    store_name=faker.company(),
                    store_owner=owner,
                    store_category=random.choice(['카페', '헤어샵', '회의실']),
                    store_description=faker.text(),
                    store_address=faker.address(),
                    store_image_url=faker.image_url(),
                    is_active=True
                )
                stores.append(store)

        # --- StoreSpace / StoreMenu / StoreMenuSpace ---
        for store in stores:
            spaces = [
                StoreSpace.objects.create(
                    store=store,
                    space_name=faker.first_name(),
                    space_image_url=faker.image_url(),
                    space_description=faker.text()
                ) for _ in range(random.randint(2, 3))  # 최소 2개 공간
            ]
            menus = [
                StoreMenu.objects.create(
                    store=store,
                    menu_name=faker.word(),
                    menu_image_url=faker.image_url(),
                    menu_cost_price=random.randint(3000, 8000),
                    menu_price=random.randint(10000, 20000)
                ) for _ in range(random.randint(2, 4))  # 최소 2개 메뉴
            ]
            for menu in menus:
                for space in spaces:
                    StoreMenuSpace.objects.create(menu=menu, space=space)

        # --- StoreItem / StoreSlot ---
        today = datetime.today().date()
        for sms in StoreMenuSpace.objects.all():
            for day_offset in range(days):
                date = today + timedelta(days=day_offset)
                for hour in hours:
                    StoreItem.objects.create(
                        menu=sms.menu,
                        space=sms.space,
                        store=sms.menu.store,
                        item_reservation_date=date,
                        item_reservation_day=date.strftime("%a"),
                        item_reservation_time=hour,
                        #item_stock=random.choice([0,1]),
                        item_stock=1,  # 항상 예약 가능
                        current_discount_rate=0.0,
                        max_discount_rate=0.3
                    )

        for space in StoreSpace.objects.all():
            for day_offset in range(days):
                date = today + timedelta(days=day_offset)
                for hour in hours:
                    StoreSlot.objects.create(
                        space=space,
                        slot_reservation_date=date,
                        slot_reservation_time=hour,
                        is_reserved=False
                    )

        # --- Reservation (고객당 1~3개 랜덤) ---
        items_with_stock = list(StoreItem.objects.filter(item_stock=1))
        for customer in customers:
            for _ in range(random.randint(1, 3)):
                if not items_with_stock:
                    break
                item = random.choice(items_with_stock)
                slot = StoreSlot.objects.filter(
                    space=item.space,
                    slot_reservation_date=item.item_reservation_date,
                    slot_reservation_time=item.item_reservation_time,
                    is_reserved=False
                ).first()
                if slot:
                    Reservation.objects.create(
                        user=customer,
                        store_item=item,
                        reservation_slot=slot,
                        reservation_cost=item.menu.menu_price
                    )
                    slot.is_reserved = True
                    slot.save()
        # for customer in customers:
        #     if StoreItem.objects.exists():
        #         item = random.choice(list(StoreItem.objects.filter(item_stock=1)))
        #         slot = StoreSlot.objects.filter(space=item.space, slot_reservation_date=item.item_reservation_date, slot_reservation_time=item.item_reservation_time, is_reserved=False).first()
        #         if slot:
        #             Reservation.objects.create(
        #                 user=customer,
        #                 store_item=item,
        #                 reservation_slot=slot,
        #                 reservation_cost=item.menu.menu_price
        #             )
        #             slot.is_reserved = True
        #             slot.save()

        # --- UserLike (고객당 2~5개 매장) ---
        for customer in customers:
            like_count = random.randint(2, 5)
            liked_stores = random.sample(stores, min(like_count, len(stores)))
            for store in liked_stores:
                UserLike.objects.create(
                    user=customer,
                    store=store
                )
        # for customer in customers:
        #     UserLike.objects.create(
        #         user=customer,
        #         store=random.choice(stores)
        #     )

        # --- StoreOperatingHour (랜덤 오픈/마감) ---
        for store in stores:
            for day in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']:
                open_time = random.randint(7, 10)  # 7~10시
                close_time = random.randint(18, 23)  # 18~23시
                StoreOperatingHour.objects.create(
                    store=store,
                    day_of_week=day,
                    open_time=open_time,
                    close_time=close_time
                )
        # for store in stores:
        #     for day in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']:
        #         StoreOperatingHour.objects.create(
        #             store=store,
        #             day_of_week=day,
        #             open_time=0,
        #             close_time=23
        #         )

        self.stdout.write(self.style.SUCCESS("✅ 더미데이터 생성 완료 (버전2)"))
