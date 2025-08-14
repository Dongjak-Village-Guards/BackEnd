from django.core.management.base import BaseCommand, CommandError
import random
from datetime import datetime, timedelta
from faker import Faker
from accounts.models import User
from stores.models import (
    Store,
    StoreSpace,
    StoreMenu,
    StoreMenuSpace,
    StoreOperatingHour,
    StoreItem,
    StoreSlot,
)
from reservations.models import Reservation, UserLike

# dongjak_addresses = [
# 이하 다 변경하기!
#     "서울특별시 동작구 사당로 123",
#     "서울특별시 동작구 보라매로 46",
#     "서울특별시 동작구 상도로 85",
#     "서울특별시 동작구 노량진로 210",
#     "서울특별시 동작구 흑석로 45",
#     "서울특별시 동작구 현충로 77",
#     "서울특별시 동작구 동작대로 55",
#     "서울특별시 동작구 신대방삼거리로 98",
#     "서울특별시 동작구 동작대로 199",
#     "서울특별시 동작구 봉천로 130",
# ]

# store_templates = [
#     {
#         "store_name": "멋진머리",
#         "category": "헤어샵",
#         "description": "도심 속 최고의 스타일리스트와 함께하는 헤어샵",
#         "image_url": "https://example.com/images/hairshop_main.jpg",
#         "spaces": [
#             {
#                 "space_name": "디자이너 1",
#                 "description": "섬세한 손길의 전문가",
#                 "image_url": "https://example.com/images/designer1.jpg"
#             },
#             {
#                 "space_name": "디자이너 2",
#                 "description": "트렌드를 선도하는 디자이너",
#                 "image_url": "https://example.com/images/designer2.jpg"
#             }
#         ],
#         "menus": [
#             {"menu_name": "커트", "image_url": "https://example.com/images/cut.jpg", "cost_price": 8000, "price": 15000},
#             {"menu_name": "파마", "image_url": "https://example.com/images/perma.jpg", "cost_price": 20000, "price": 45000},
#             {"menu_name": "염색", "image_url": "https://example.com/images/dye.jpg", "cost_price": 15000, "price": 35000}
#         ]
#     },
#     {
#         "store_name": "달콤카페",
#         "category": "카페",
#         "description": "아늑하고 포근한 분위기의 카페",
#         "image_url": "https://example.com/images/cafe_main.jpg",
#         "spaces": [
#             {
#                 "space_name": "창가 자리",
#                 "description": "햇살 가득한 창가 자리",
#                 "image_url": "https://example.com/images/window_seat.jpg"
#             },
#             {
#                 "space_name": "테라스 자리",
#                 "description": "바람이 상쾌한 테라스 자리",
#                 "image_url": "https://example.com/images/terrace.jpg"
#             }
#         ],
#         "menus": [
#             {"menu_name": "아메리카노", "image_url": "https://example.com/images/americano.jpg", "cost_price": 1000, "price": 4000},
#             {"menu_name": "카페라떼", "image_url": "https://example.com/images/latte.jpg", "cost_price": 1300, "price": 4500}
#         ]
#     }
# ]


# TODO 주소값 실제데이터로 변경하기
# TODO is_dummy 필드를 모델들에 포함시켜서 추후 삭제 가능하게 변경하기
class Command(BaseCommand):
    help = "전체 더미데이터 생성 (ItemRecord 제외) - 완전 통합 버전"

    def add_arguments(self, parser):
        parser.add_argument("--dev", action="store_true", help="개발 DB에 생성")
        parser.add_argument(
            "--prod", action="store_true", help="운영 DB에 생성 (확인 필요)"
        )
        parser.add_argument(
            "--skip-delete", action="store_true", help="기존 데이터 삭제 없이 추가"
        )
        parser.add_argument("--owners", type=int, default=10)
        parser.add_argument("--customers", type=int, default=10)
        parser.add_argument("--stores", type=int, default=10)
        parser.add_argument("--days", type=int, default=14)
        parser.add_argument(
            "--hours",
            nargs="+",
            type=int,
            default=list(range(24)),
            help="시간 슬롯 목록 (기본 0~23)",
        )

    def handle(self, *args, **options):
        if not options["dev"] and not options["prod"]:
            raise CommandError("--dev 또는 --prod 옵션 중 하나를 지정하세요.")

        if options["prod"]:
            self.stdout.write(self.style.WARNING("⚠ 운영 DB에서 실행됩니다."))
            confirm = input("정말 실행하시겠습니까? (YES 입력) : ")
            if confirm != "YES":
                self.stdout.write(self.style.ERROR("취소됨"))
                return

        faker = Faker("ko_KR")  # 한국어로!
        days = options["days"]
        hours = options["hours"]

        # --- 기존 데이터 삭제 ---
        if not options["skip_delete"]:
            Reservation.objects.filter(is_dummy=True).delete()
            UserLike.objects.filter(is_dummy=True).delete()
            StoreOperatingHour.objects.filter(is_dummy=True).delete()
            StoreItem.objects.filter(is_dummy=True).delete()
            StoreSlot.objects.filter(is_dummy=True).delete()
            StoreMenuSpace.objects.filter(is_dummy=True).delete()
            StoreMenu.objects.filter(is_dummy=True).delete()
            StoreSpace.objects.filter(is_dummy=True).delete()
            Store.objects.filter(is_dummy=True).delete()
            User.objects.filter(is_dummy=True).delete()  # ?

        # ⬅ 추가: 기존 고객 할인액 전부 0으로 초기화
        User.objects.filter(user_role="customer").update(user_discounted_cost_sum=0)

        # --- Users ---
        owners = [
            # 가짜주소 버전
            User.objects.create(
                user_email=faker.unique.email(),
                user_image_url=faker.image_url(),
                user_password=faker.password(),
                user_role="owner",
                user_address=faker.address(),
                user_discounted_cost_sum=0,
                is_dummy=True,  # 더미데이터 표시
            )
            # AbstractUser
            # User.objects.create_user(
            #     user_email=faker.unique.email(),
            #     password="dummy_owner_pw",  # 해시 저장됨
            #     user_image_url=faker.image_url(),
            #     user_role="owner",
            #     user_address=faker.address(),
            #     user_discounted_cost_sum=0,
            #     is_dummy=True,
            # )
            # 진짜주소 버전
            # User.objects.create(
            #     user_email=faker.unique.email(),
            #     user_image_url=faker.image_url(),
            #     user_password=faker.password(),
            #     user_role='owner',
            #     user_address=random.choice(dongjak_addresses),
            #     user_discounted_cost_sum=0,
            #     is_dummy=True
            # )
            for _ in range(options["owners"])
        ]
        customers = [
            # 가짜주소 버전
            User.objects.create(
                user_email=faker.unique.email(),
                user_image_url=faker.image_url(),
                user_password=faker.password(),
                user_role="customer",
                user_address=faker.address(),
                user_discounted_cost_sum=0,
                is_dummy=True,  # 더미데이터 표시
            )
            # AbstractUser
            # User.objects.create_user(
            #     user_email=faker.unique.email(),
            #     password="dummy_customer_pw",  # 해시 저장됨
            #     user_image_url=faker.image_url(),
            #     user_role="customer",
            #     user_address=faker.address(),
            #     user_discounted_cost_sum=0,
            #     is_dummy=True,
            # )
            # 진짜주소 버전
            # User.objects.create(
            #     user_email=faker.unique.email(),
            #     user_image_url=faker.image_url(),
            #     user_password=faker.password(),
            #     user_role='customer',
            #     user_address=random.choice(dongjak_addresses),
            #     user_discounted_cost_sum=0,
            #     is_dummy=True
            # )
            for _ in range(options["customers"])
        ]

        # --- Stores ---
        stores = []
        stores_per_owner = max(1, options["stores"] // len(owners))
        for owner in owners:
            for _ in range(stores_per_owner):
                # 가짜주소 버전
                store = Store.objects.create(
                    store_name=faker.company(),
                    store_owner=owner,
                    store_category=random.choice(["카페", "헤어샵", "회의실"]),
                    store_description=faker.text(),
                    store_address=faker.address(),
                    store_image_url=faker.image_url(),
                    is_active=True,
                    is_dummy=True,  # 더미데이터 표시
                )
                # 진짜주소 버전
                # template = random.choice(store_templates)
                # store = Store.objects.create(
                #     store_name=template["store_name"],
                #     store_owner=owner,
                #     store_category=template["category"],
                #     store_description=template["description"],
                #     store_address=random.choice(dongjak_addresses),
                #     store_image_url=template["image_url"],
                #     is_active=True,
                #     is_dummy=True
                # )
                stores.append(store)

        # --- StoreSpace / StoreMenu / StoreMenuSpace ---
        for store in stores:
            # 가짜주소 버전
            spaces = [
                StoreSpace.objects.create(
                    store=store,
                    space_name=faker.first_name(),
                    space_image_url=faker.image_url(),
                    space_description=faker.text(),
                    is_dummy=True,  # 더미데이터 표시
                )
                for _ in range(random.randint(2, 3))  # 최소 2개 공간
            ]
            # 진짜주소 버전
            # spaces = []
            # for space_t in template["spaces"]:
            #     spaces.append(StoreSpace.objects.create(
            #         store=store,
            #         space_name=space_t["space_name"],
            #         space_image_url=space_t["image_url"],
            #         space_description=space_t["description"],
            #         is_dummy=True
            #     ))

            # 가짜주소 버전
            menus = [
                StoreMenu.objects.create(
                    store=store,
                    menu_name=faker.word(),
                    menu_image_url=faker.image_url(),
                    menu_cost_price=random.randint(3000, 8000),
                    menu_price=random.randint(10000, 20000),
                    is_dummy=True,  # 더미데이터 표시
                )
                for _ in range(random.randint(2, 4))  # 최소 2개 메뉴
            ]
            # 진짜주소 버전
            # menus = []
            # for menu_t in template["menus"]:
            #     menu = StoreMenu.objects.create(
            #         store=store,
            #         menu_name=menu_t["menu_name"],
            #         menu_image_url=menu_t["image_url"],
            #         menu_cost_price=menu_t["cost_price"],
            #         menu_price=menu_t["price"],
            #         is_dummy=True
            #     )
            #     for space in spaces:
            #         StoreMenuSpace.objects.create(
            #             menu=menu,
            #             space=space,
            #             is_dummy=True
            #         )
            for menu in menus:
                for space in spaces:
                    StoreMenuSpace.objects.create(
                        menu=menu, space=space, is_dummy=True  # 더미데이터 표시
                    )

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
                        # item_stock=random.choice([0,1]), /또는
                        # item_stock=1,  # 항상 예약 가능
                        # current_discount_rate=0.0, /또는
                        item_stock=random.choice([0, 1]),
                        current_discount_rate=round(random.uniform(0.0, 0.3), 2),
                        max_discount_rate=0.3,
                        is_dummy=True,  # 더미데이터 표시
                    )

        for space in StoreSpace.objects.all():
            for day_offset in range(days):
                date = today + timedelta(days=day_offset)
                for hour in hours:
                    StoreSlot.objects.create(
                        space=space,
                        slot_reservation_date=date,
                        slot_reservation_time=hour,
                        is_reserved=False,
                        is_dummy=True,  # 더미데이터 표시
                    )

        # --- Reservation 생성 (고객당 1~3개 랜덤) ---
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
                    is_reserved=False,
                ).first()

                if slot:
                    # 할인 적용된 가격
                    discounted_price = round(
                        item.menu.menu_price * (1 - item.current_discount_rate)
                    )
                    Reservation.objects.create(
                        user=customer,
                        store_item=item,
                        reservation_slot=slot,
                        reservation_cost=discounted_price,
                        is_dummy=True,  # 더미데이터 표시
                    )

                    # 1) 고객 할인 금액 누적
                    discount_amount = item.menu.menu_price * item.current_discount_rate
                    customer.user_discounted_cost_sum += discount_amount
                    customer.save()

                    # 2) 아이템 재고 차감
                    item.item_stock = 0
                    item.save()

                    # 3) 슬롯 예약
                    slot.is_reserved = True
                    slot.save()

                    # 4) 중복 예약 방지
                    items_with_stock.remove(item)

                    # 5) 매장 is_active 업데이트
                    store = item.store
                    has_stock = store.storeitem_set.filter(item_stock__gt=0).exists()
                    store.is_active = has_stock
                    store.save()

        # --- UserLike (고객당 2~5개 매장) ---
        for customer in customers:
            like_count = random.randint(2, 5)
            liked_stores = random.sample(stores, min(like_count, len(stores)))
            for store in liked_stores:
                UserLike.objects.create(
                    user=customer, store=store, is_dummy=True  # 더미데이터 표시
                )

        # --- StoreOperatingHour (랜덤 오픈/마감) ---
        for store in stores:
            for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
                open_time = random.randint(7, 10)  # 7~10시
                close_time = random.randint(18, 23)  # 18~23시
                StoreOperatingHour.objects.create(
                    store=store,
                    day_of_week=day,
                    open_time=open_time,
                    close_time=close_time,
                    is_dummy=True,  # 더미데이터 표시
                )

        self.stdout.write(
            self.style.SUCCESS(
                "✅ 더미데이터 생성 완료 (is_dummy 추가, 아직 가짜주소!)"
            )
        )


# 실행 시 buynow % python manage.py generate_dummy_data --dev --owners 10 --customers 10 --stores 10 --days 14
# 숫자는 상황에 맞게 변경 가능 (실행 전 상의 필수!)
