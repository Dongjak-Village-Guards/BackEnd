# from stores.data.dongjak_addresses import dongjak_addresses
# from stores.data.dummy_store_templates import store_templates

# from django.core.management.base import BaseCommand, CommandError
# import random
# from datetime import datetime, timedelta
# from faker import Faker
# from accounts.models import User
# from stores.models import (
#     Store,
#     StoreSpace,
#     StoreMenu,
#     StoreMenuSpace,
#     StoreOperatingHour,
#     StoreItem,
#     StoreSlot,
# )
# from reservations.models import Reservation, UserLike
# class Command(BaseCommand):
#     help = "전체 더미데이터 생성 (ItemRecord 제외) - 완전 통합 버전"

#     def add_arguments(self, parser):
#         parser.add_argument("--dev", action="store_true", help="개발 DB에 생성")
#         parser.add_argument(
#             "--prod", action="store_true", help="운영 DB에 생성 (확인 필요)"
#         )
#         parser.add_argument(
#             "--skip-delete", action="store_true", help="기존 데이터 삭제 없이 추가"
#         )
#         parser.add_argument("--owners", type=int, default=10)
#         parser.add_argument("--customers", type=int, default=10)
#         parser.add_argument("--stores", type=int, default=10)
#         parser.add_argument("--days", type=int, default=14)
#         parser.add_argument(
#             "--hours",
#             nargs="+",
#             type=int,
#             default=list(range(24)),
#             help="시간 슬롯 목록 (기본 0~23)",
#         )

#     def handle(self, *args, **options):
#         if not options["dev"] and not options["prod"]:
#             raise CommandError("--dev 또는 --prod 옵션 중 하나를 지정하세요.")

#         if options["prod"]:
#             self.stdout.write(self.style.WARNING("⚠ 운영 DB에서 실행됩니다."))
#             confirm = input("정말 실행하시겠습니까? (YES 입력) : ")
#             if confirm != "YES":
#                 self.stdout.write(self.style.ERROR("취소됨"))
#                 return

#         faker = Faker("ko_KR")  # 한국어로!
#         days = options["days"]
#         hours = options["hours"]

#         # --- 기존 데이터 삭제 ---
#         if not options["skip_delete"]:
#             Reservation.objects.filter(is_dummy=True).delete()
#             UserLike.objects.filter(is_dummy=True).delete()
#             StoreOperatingHour.objects.filter(is_dummy=True).delete()
#             StoreItem.objects.filter(is_dummy=True).delete()
#             StoreSlot.objects.filter(is_dummy=True).delete()
#             StoreMenuSpace.objects.filter(is_dummy=True).delete()
#             StoreMenu.objects.filter(is_dummy=True).delete()
#             StoreSpace.objects.filter(is_dummy=True).delete()
#             Store.objects.filter(is_dummy=True).delete()
#             User.objects.filter(is_dummy=True).delete()  # ?

#         # ⬅ 추가: 기존 고객 할인액 전부 0으로 초기화
#         User.objects.filter(user_role="customer").update(user_discounted_cost_sum=0)

#         # --- 주소 & 템플릿 중복 방지용 준비 ---
#         # [변경됨] 주소 리스트를 랜덤 섞은 후 pop()으로 하나씩 사용
#         address_pool = random.sample(dongjak_addresses, len(dongjak_addresses))  # ← 모든 주소 무작위 순서

#         # [변경됨] 가게 템플릿도 필요 개수만큼 중복 없이 추출
#         selected_templates = random.sample(store_templates, options["stores"])  # ← 중복 없는 템플릿 목록

#         # --- Users ---
#         owners = [
#             User.objects.create_user(
#                 user_email=faker.unique.email(),
#                 password="dummy_owner_pw",  # 해시 저장됨
#                 user_image_url=faker.image_url(),
#                 user_role="owner",
#                 # user_address=random.choice(dongjak_addresses),
#                 user_address=address_pool.pop(),  # 한 번 쓰고 제거
#                 user_discounted_cost_sum=0,
#                 is_dummy=True,
#             )
#             for _ in range(options["owners"])
#         ]
#         customers = [
#             User.objects.create_user(
#                 user_email=faker.unique.email(),
#                 password="dummy_customer_pw",
#                 user_image_url=faker.image_url(),
#                 user_role="customer",
#                 # user_address=random.choice(dongjak_addresses),
#                 user_address=address_pool.pop(),  # 한 번 쓰고 제거
#                 user_discounted_cost_sum=0,
#                 is_dummy=True,
#             )
#             for _ in range(options["customers"])
#         ]

#         # Store와 Template을 함께 저장할 리스트 생성
#         store_template_pairs = []
#         stores_per_owner = max(1, options["stores"] // len(owners))
#         template_index = 0  # 템플릿 순회용 인덱스

#         for owner in owners:
#             for _ in range(stores_per_owner):
#                 template = selected_templates[template_index]  # 중복 없는 템플릿 선택
#                 template_index += 1

#                 store = Store.objects.create(
#                     store_name=template["store_name"],
#                     store_owner=owner,
#                     store_category=template["category"],
#                     store_description=template["description"],
#                     store_address=address_pool.pop(),  # 고유 주소 배정
#                     store_image_url=template["image_url"],
#                     is_active=True,
#                     is_dummy=True,
#                 )
#                 stores.append(store)
#                 store_template_pairs.append((store, template))  # 매장과 템플릿을 페어로 저장

#         # --- StoreSpace / StoreMenu / StoreMenuSpace ---
#         for store, template in store_template_pairs:
#             spaces = []
#             # 공간 생성
#             for space_t in template["spaces"]:
#                 space = StoreSpace.objects.create(
#                     store=store,
#                     space_name=space_t["space_name"],
#                     space_image_url=space_t["image_url"],
#                     space_description=space_t["description"],
#                     is_dummy=True,
#                 )
#                 spaces.append(space)

#             # 메뉴 생성과 공간 매핑
#             for menu_t in template["menus"]:
#                 menu = StoreMenu.objects.create(
#                     store=store,
#                     menu_name=menu_t["menu_name"],
#                     menu_image_url=menu_t["image_url"],
#                     menu_cost_price=menu_t["cost_price"],
#                     menu_price=menu_t["price"],
#                     is_dummy=True,
#                 )
#                 for space in spaces:
#                     StoreMenuSpace.objects.create(menu=menu, space=space, is_dummy=True)

#         # ==================== [변경 끝] ====================

#         # --- StoreItem / StoreSlot ---
#         today = datetime.today().date()
#         for sms in StoreMenuSpace.objects.all():
#             for day_offset in range(days):
#                 date = today + timedelta(days=day_offset)
#                 for hour in hours:
#                     StoreItem.objects.create(
#                         menu=sms.menu,
#                         space=sms.space,
#                         store=sms.menu.store,
#                         item_reservation_date=date,
#                         item_reservation_day=date.strftime("%a"),
#                         item_reservation_time=hour,
#                         # item_stock=random.choice([0,1]), /또는
#                         # item_stock=1,  # 항상 예약 가능
#                         # current_discount_rate=0.0, /또는
#                         item_stock=random.choice([0, 1]),
#                         current_discount_rate=round(random.uniform(0.0, 0.3), 2),
#                         max_discount_rate=0.3,
#                         is_dummy=True,  # 더미데이터 표시
#                     )

#         for space in StoreSpace.objects.all():
#             for day_offset in range(days):
#                 date = today + timedelta(days=day_offset)
#                 for hour in hours:
#                     StoreSlot.objects.create(
#                         space=space,
#                         slot_reservation_date=date,
#                         slot_reservation_time=hour,
#                         is_reserved=False,
#                         is_dummy=True,  # 더미데이터 표시
#                     )

#         # --- Reservation 생성 (고객당 1~3개 랜덤) ---
#         items_with_stock = list(StoreItem.objects.filter(item_stock=1))
#         for customer in customers:
#             for _ in range(random.randint(1, 3)):
#                 if not items_with_stock:
#                     break

#                 item = random.choice(items_with_stock)
#                 slot = StoreSlot.objects.filter(
#                     space=item.space,
#                     slot_reservation_date=item.item_reservation_date,
#                     slot_reservation_time=item.item_reservation_time,
#                     is_reserved=False,
#                 ).first()

#                 if slot:
#                     # 할인 적용된 가격
#                     discounted_price = round(
#                         item.menu.menu_price * (1 - item.current_discount_rate)
#                     )
#                     Reservation.objects.create(
#                         user=customer,
#                         store_item=item,
#                         reservation_slot=slot,
#                         reservation_cost=discounted_price,
#                         is_dummy=True,  # 더미데이터 표시
#                     )

#                     # 1) 고객 할인 금액 누적
#                     discount_amount = item.menu.menu_price * item.current_discount_rate
#                     customer.user_discounted_cost_sum += discount_amount
#                     customer.save()

#                     # 2) 아이템 재고 차감
#                     item.item_stock = 0
#                     item.save()

#                     # 3) 슬롯 예약
#                     slot.is_reserved = True
#                     slot.save()

#                     # 4) 중복 예약 방지
#                     items_with_stock.remove(item)

#                     # 5) 매장 is_active 업데이트
#                     store = item.store
#                     has_stock = store.storeitem_set.filter(item_stock__gt=0).exists()
#                     store.is_active = has_stock
#                     store.save()

#         # --- UserLike (고객당 2~5개 매장) ---
#         for customer in customers:
#             like_count = random.randint(2, 5)
#             if stores:  # stores가 비어있지 않을 때만 실행
#                 liked_stores = random.sample(stores, min(like_count, len(stores)))
#                 for store in liked_stores:
#                     UserLike.objects.create(user=customer, store=store, is_dummy=True)
#             # liked_stores = random.sample(stores, min(like_count, len(stores)))
#             for store in liked_stores:
#                 UserLike.objects.create(
#                     user=customer, store=store, is_dummy=True  # 더미데이터 표시
#                 )

#         # --- StoreOperatingHour (랜덤 오픈/마감) ---
#         for store in stores:
#             for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
#                 open_time = random.randint(7, 10)  # 7~10시
#                 close_time = random.randint(18, 23)  # 18~23시
#                 StoreOperatingHour.objects.create(
#                     store=store,
#                     day_of_week=day,
#                     open_time=open_time,
#                     close_time=close_time,
#                     is_dummy=True,  # 더미데이터 표시
#                 )

#         self.stdout.write(
#             self.style.SUCCESS(
#                 "✅ 더미데이터 생성 완료 (진짜같은 주소 적용)"
#             )
#         )

# from stores.data.dongjak_addresses import dongjak_addresses
# from stores.data.dummy_store_templates import store_templates

# from django.core.management.base import BaseCommand, CommandError
# import random
# from datetime import datetime, timedelta
# from faker import Faker
# from accounts.models import User
# from stores.models import (
#     Store,
#     StoreSpace,
#     StoreMenu,
#     StoreMenuSpace,
#     StoreOperatingHour,
#     StoreItem,
#     StoreSlot,
# )
# from reservations.models import Reservation, UserLike


# class Command(BaseCommand):
#     help = "전체 더미데이터 생성 (ItemRecord 제외) - 완전 통합 버전"

#     def add_arguments(self, parser):
#         parser.add_argument("--dev", action="store_true", help="개발 DB에 생성")
#         parser.add_argument(
#             "--prod", action="store_true", help="운영 DB에 생성 (확인 필요)"
#         )
#         parser.add_argument(
#             "--skip-delete", action="store_true", help="기존 데이터 삭제 없이 추가"
#         )
#         parser.add_argument("--owners", type=int, default=10)
#         parser.add_argument("--customers", type=int, default=10)
#         parser.add_argument("--stores", type=int, default=10)
#         parser.add_argument("--days", type=int, default=14)
#         parser.add_argument(
#             "--hours",
#             nargs="+",
#             type=int,
#             default=list(range(24)),
#             help="시간 슬롯 목록 (기본 0~23)",
#         )

#     def handle(self, *args, **options):
#         if not options["dev"] and not options["prod"]:
#             raise CommandError("--dev 또는 --prod 옵션 중 하나를 지정하세요.")

#         if options["prod"]:
#             self.stdout.write(self.style.WARNING("⚠ 운영 DB에서 실행됩니다."))
#             confirm = input("정말 실행하시겠습니까? (YES 입력) : ")
#             if confirm != "YES":
#                 self.stdout.write(self.style.ERROR("취소됨"))
#                 return

#         faker = Faker("ko_KR")  # 한국어로!
#         days = options["days"]
#         hours = options["hours"]

#         # --- 기존 데이터 삭제 ---
#         if not options["skip_delete"]:
#             Reservation.objects.filter(is_dummy=True).delete()
#             UserLike.objects.filter(is_dummy=True).delete()
#             StoreOperatingHour.objects.filter(is_dummy=True).delete()
#             StoreItem.objects.filter(is_dummy=True).delete()
#             StoreSlot.objects.filter(is_dummy=True).delete()
#             StoreMenuSpace.objects.filter(is_dummy=True).delete()
#             StoreMenu.objects.filter(is_dummy=True).delete()
#             StoreSpace.objects.filter(is_dummy=True).delete()
#             Store.objects.filter(is_dummy=True).delete()
#             User.objects.filter(is_dummy=True).delete()

#         # 기존 고객 할인액 초기화
#         User.objects.filter(user_role="customer").update(user_discounted_cost_sum=0)

#         # --- 주소 & 템플릿 준비 ---
#         address_pool = random.sample(
#             dongjak_addresses, len(dongjak_addresses)
#         )  # 랜덤 주소 풀
#         selected_templates = random.sample(
#             store_templates, options["stores"]
#         )  # 랜덤 템플릿 풀

#         # 안전하게 주소 pop하는 함수 정의 (주소 부족 방지)
#         def safe_pop_address():
#             return address_pool.pop() if address_pool else faker.address()

#         # --- Users 생성 ---
#         owners = [
#             User.objects.create_user(
#                 user_email=faker.unique.email(),
#                 password="dummy_owner_pw",
#                 user_image_url=faker.image_url(),
#                 user_role="owner",
#                 user_address=safe_pop_address(),  # 안전 pop 사용
#                 user_discounted_cost_sum=0,
#                 is_dummy=True,
#             )
#             for _ in range(options["owners"])
#         ]
#         customers = [
#             User.objects.create_user(
#                 user_email=faker.unique.email(),
#                 password="dummy_customer_pw",
#                 user_image_url=faker.image_url(),
#                 user_role="customer",
#                 user_address=safe_pop_address(),  # 안전 pop 사용
#                 user_discounted_cost_sum=0,
#                 is_dummy=True,
#             )
#             for _ in range(options["customers"])
#         ]

#         # --- Store 생성 ---
#         stores = []  # stores 리스트를 handle 전역 스코프에서 초기화
#         store_template_pairs = []
#         stores_per_owner = max(1, options["stores"] // len(owners))
#         template_index = 0

#         for owner in owners:
#             for _ in range(stores_per_owner):
#                 if template_index >= len(
#                     selected_templates
#                 ):  # template index 초과 방지
#                     break
#                 template = selected_templates[template_index]
#                 template_index += 1
#                 store = Store.objects.create(
#                     store_name=template["store_name"],
#                     store_owner=owner,
#                     store_category=template["category"],
#                     store_description=template["description"],
#                     store_address=safe_pop_address(),
#                     store_image_url=template["image_url"],
#                     is_active=True,
#                     is_dummy=True,
#                 )
#                 stores.append(store)
#                 store_template_pairs.append((store, template))

#         # --- StoreSpace / StoreMenu / StoreMenuSpace ---
#         for store, template in store_template_pairs:
#             spaces = []
#             # 공간 생성하는 부분
#             for space_t in template["spaces"]:
#                 space = StoreSpace.objects.create(
#                     store=store,
#                     space_name=space_t["space_name"],
#                     space_image_url=space_t["image_url"],
#                     space_description=space_t["description"],
#                     is_dummy=True,
#                 )
#                 spaces.append(space)
#             # 메뉴 생성, 공간 매핑
#             for menu_t in template["menus"]:
#                 menu = StoreMenu.objects.create(
#                     store=store,
#                     menu_name=menu_t["menu_name"],
#                     menu_image_url=menu_t["image_url"],
#                     menu_cost_price=menu_t["cost_price"],
#                     menu_price=menu_t["price"],
#                     is_dummy=True,
#                 )
#                 for space in spaces:
#                     StoreMenuSpace.objects.create(menu=menu, space=space, is_dummy=True)

#         # --- StoreItem / StoreSlot ---
#         today = datetime.today().date()
#         for sms in StoreMenuSpace.objects.all():
#             for day_offset in range(days):
#                 date = today + timedelta(days=day_offset)
#                 for hour in hours:
#                     StoreItem.objects.create(
#                         menu=sms.menu,
#                         space=sms.space,
#                         store=sms.menu.store,
#                         item_reservation_date=date,
#                         item_reservation_day=date.strftime("%a"),
#                         item_reservation_time=hour,
#                         item_stock=random.choice([0, 1]),
#                         current_discount_rate=round(random.uniform(0.0, 0.3), 2),
#                         max_discount_rate=0.3,
#                         is_dummy=True,
#                     )
#         for space in StoreSpace.objects.all():
#             for day_offset in range(days):
#                 date = today + timedelta(days=day_offset)
#                 for hour in hours:
#                     StoreSlot.objects.create(
#                         space=space,
#                         slot_reservation_date=date,
#                         slot_reservation_time=hour,
#                         is_reserved=False,
#                         is_dummy=True,
#                     )

#         # --- Reservations ---
#         items_with_stock = list(StoreItem.objects.filter(item_stock=1))
#         for customer in customers:
#             for _ in range(random.randint(1, 3)):
#                 if not items_with_stock:
#                     break
#                 item = random.choice(items_with_stock)
#                 slot = StoreSlot.objects.filter(
#                     space=item.space,
#                     slot_reservation_date=item.item_reservation_date,
#                     slot_reservation_time=item.item_reservation_time,
#                     is_reserved=False,
#                 ).first()
#                 if slot:
#                     discounted_price = round(
#                         item.menu.menu_price * (1 - item.current_discount_rate)
#                     )
#                     Reservation.objects.create(
#                         user=customer,
#                         store_item=item,
#                         reservation_slot=slot,
#                         reservation_cost=discounted_price,
#                         is_dummy=True,
#                     )
#                     # 할인받은 금액 누적
#                     discount_amount = item.menu.menu_price * item.current_discount_rate
#                     customer.user_discounted_cost_sum += discount_amount
#                     customer.save()
#                     # 아이템 재고 차감 (상태변화에 가깝긴 함)
#                     item.item_stock = 0
#                     item.save()
#                     # 슬롯 예약됨으로 처리
#                     slot.is_reserved = True
#                     slot.save()
#                     # 중복 예약 방지
#                     items_with_stock.remove(item)
#                     # 매장 is_active 업데이트
#                     store = item.store
#                     store.is_active = store.storeitem_set.filter(
#                         item_stock__gt=0
#                     ).exists()
#                     store.save()

#         # --- UserLike ---
#         for customer in customers:
#             like_count = random.randint(2, 5)
#             if stores:  # [추가] stores 비어있을 때 방어
#                 liked_stores = random.sample(stores, min(like_count, len(stores)))
#                 for store in liked_stores:
#                     UserLike.objects.create(user=customer, store=store, is_dummy=True)

#         # --- StoreOperatingHour ---
#         for store in stores:
#             for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
#                 open_time = random.randint(7, 10)
#                 close_time = random.randint(18, 23)
#                 StoreOperatingHour.objects.create(
#                     store=store,
#                     day_of_week=day,
#                     open_time=open_time,
#                     close_time=close_time,
#                     is_dummy=True,
#                 )

#         self.stdout.write(
#             self.style.SUCCESS("✅ 더미데이터 생성 완료 (진짜같은 주소 적용...!)")
#         )

# 실행 시 buynow % python manage.py generate_dummy_data --dev --owners 10 --customers 10 --stores 10 --days 14
# 숫자는 상황에 맞게 변경 가능 (실행 전 상의 필수!)

from stores.data.dongjak_addresses import dongjak_addresses
from stores.data.dummy_store_templates import store_templates

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


class Command(BaseCommand):
    help = "전체 더미데이터 생성 (ItemRecord 제외) - 0820 수정"

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

        # 기존 더미 데이터 삭제 (옵션 미사용시)
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
            User.objects.filter(is_dummy=True).delete()

        # 기존 고객 할인액 초기화
        User.objects.filter(user_role="customer").update(user_discounted_cost_sum=0)

        # --- 주소 & 템플릿 준비 ---
        address_pool = random.sample(
            dongjak_addresses, len(dongjak_addresses)
        )  # 랜덤 주소 풀
        selected_templates = random.sample(
            store_templates, options["stores"]
        )  # 랜덤 템플릿 풀

        def safe_pop_address():
            return address_pool.pop() if address_pool else faker.address()

        # --- Users 생성(점주/고객) ---
        owners = [
            User.objects.create_user(
                user_email=faker.unique.email(),
                password="dummy_owner_pw",
                user_image_url=faker.image_url(),
                user_role="owner",
                user_address=safe_pop_address(),
                user_discounted_cost_sum=0,
                is_dummy=True,
            )
            for _ in range(options["owners"])
        ]
        customers = []
        # customers = [
        #     User.objects.create_user(
        #         user_email=faker.unique.email(),
        #         password="dummy_customer_pw",
        #         user_image_url=faker.image_url(),
        #         user_role="customer",
        #         user_address=safe_pop_address(),
        #         user_discounted_cost_sum=0,
        #         is_dummy=True,
        #     )
        #     for _ in range(options["customers"])
        # ]

        # --- Store 생성 (점주당 1개 이상 매장 소유) ---
        stores = []
        store_template_pairs = []
        stores_per_owner = max(1, options["stores"] // len(owners))
        template_index = 0

        for owner in owners:
            for _ in range(stores_per_owner):
                if template_index >= len(selected_templates):
                    break
                template = selected_templates[template_index]
                template_index += 1
                store = Store.objects.create(
                    store_name=template["store_name"],
                    store_owner=owner,
                    store_category=template["category"],
                    store_description=template["description"],
                    store_address=safe_pop_address(),
                    store_image_url=template["image_url"],
                    is_active=True,
                    is_dummy=True,
                )
                stores.append(store)
                store_template_pairs.append((store, template))

        # ----- [코드수정 시작: StoreMenu, StoreSpace, StoreMenuSpace 구조 개선 및 가중치/할인 정책 추가] -----
        for store, template in store_template_pairs:
            # 1. 매장별 전용 메뉴를 먼저 만듭니다.
            menu_objs = []
            for menu_t in template["menus"]:
                # 메뉴별 de_weight와 max_discount_rate를 각기 다르게 랜덤 할당
                de_weight = round(random.uniform(0.1, 5.0), 2)
                max_discount = round(random.uniform(0.15, 0.5), 2)  # 15~50%
                menu = StoreMenu.objects.create(
                    store=store,
                    menu_name=menu_t["menu_name"],
                    menu_image_url=menu_t["image_url"],
                    menu_cost_price=menu_t["cost_price"],
                    menu_price=menu_t["price"],
                    de_weight=de_weight,
                    is_dummy=True,
                )
                # StoreMenu에는 max_discount_rate 필드가 없으므로,
                # StoreItem에서 메뉴별로 이 값을 나중에 사용하기 위해 tuple 형태로 저장
                menu_objs.append((menu, max_discount))

            # 2. space 생성 (각 매장 내부의 공간), 주어진 템플릿 그대로
            spaces = []
            for space_t in template["spaces"]:
                space = StoreSpace.objects.create(
                    store=store,
                    space_name=space_t["space_name"],
                    space_image_url=space_t["image_url"],
                    space_description=space_t["description"],
                    is_dummy=True,
                )
                spaces.append(space)

            # 3. **공간별 메뉴 배정 방식 개선**
            # 각 space마다 1개~매장 전체의 메뉴 중 무작위 일부만 배정(중복, 누락, 샘플링 모두 허용)
            for space in spaces:
                space_menu_count = random.randint(1, len(menu_objs))
                sampled_menus = random.sample(menu_objs, space_menu_count)
                for menu, max_discount in sampled_menus:
                    StoreMenuSpace.objects.create(menu=menu, space=space, is_dummy=True)
                    # StoreItem을 만들 때 이 연결 정보가 사용됨
        # ----- [코드수정 끝] -----

        # ----- [코드수정 시작: StoreItem current_discount_rate 고정, max_discount_rate 다양화, 재고 비율 ↑] -----
        today = datetime.today().date()
        # StoreMenuSpace에 대해 StoreItem 생성
        for sms in StoreMenuSpace.objects.all():
            # 각 StoreMenuSpace의 메뉴에 해당하는 max_discount_rate를 menu_objs에서 찾아서 적용(없으면 0.3)
            # menu_objs 변수가 store 스코프 밖에서도 접근 가능해야 하지만, 여기선 defaults로 0.3 처리
            menu = sms.menu
            # 가게에 속한 모든 menu_objs 중, sms.menu에 해당하는 max_discount 찾아내기
            try:
                matched = [
                    m
                    for s, t in store_template_pairs
                    if s == menu.store
                    for m in [
                        (
                            x,
                            round(random.uniform(0.15, 0.5), 2),
                        )  # 임시 랜덤, 아래에서 더 정확히 조인 가능
                        for x in StoreMenu.objects.filter(
                            store=s, menu_name=menu.menu_name, is_dummy=True
                        )
                    ]
                    if x[0] == menu
                ]
                max_discount_rate = matched[1] if matched else 0.3
            except Exception:
                max_discount_rate = 0.3

            # 80% 이상 확률로 재고 1, 나머지 0 -> 그냥 재고 1로 고정
            for day_offset in range(days):
                date = today + timedelta(days=day_offset)
                for hour in hours:
                    # stock = 1 if random.random() < 0.85 else 0  # 비율 ↑
                    stock = 1  # 재고 1로 고정
                    StoreItem.objects.create(
                        menu=sms.menu,
                        space=sms.space,
                        store=sms.menu.store,
                        item_reservation_date=date,
                        item_reservation_day=date.strftime("%a"),
                        item_reservation_time=hour,
                        item_stock=stock,
                        current_discount_rate=0.1,  # 항상 1.0
                        max_discount_rate=max_discount_rate,
                        is_dummy=True,
                    )
        # ----- [코드수정 끝] -----

        # StoreSlot(시간 예약 슬롯) 생성: 각 공간별 날짜/시간 기준 예약 정보 초기화
        for space in StoreSpace.objects.all():
            for day_offset in range(days):
                date = today + timedelta(days=day_offset)
                for hour in hours:
                    StoreSlot.objects.create(
                        space=space,
                        slot_reservation_date=date,
                        slot_reservation_time=hour,
                        is_reserved=False,
                        is_dummy=True,
                    )

        # # 예약(Reservation) 객체 생성: 고객들이 랜덤하게 예약/재고 차감/매장 활성여부 갱신 등
        # items_with_stock = list(StoreItem.objects.filter(item_stock=1))
        # for customer in customers:
        #     for _ in range(random.randint(1, 3)):
        #         if not items_with_stock:
        #             break
        #         item = random.choice(items_with_stock)
        #         slot = StoreSlot.objects.filter(
        #             space=item.space,
        #             slot_reservation_date=item.item_reservation_date,
        #             slot_reservation_time=item.item_reservation_time,
        #             is_reserved=False,
        #         ).first()
        #         if slot:
        #             discounted_price = round(
        #                 item.menu.menu_price * (1 - item.current_discount_rate)
        #             )
        #             Reservation.objects.create(
        #                 user=customer,
        #                 store_item=item,
        #                 reservation_slot=slot,
        #                 reservation_cost=discounted_price,
        #                 is_dummy=True,
        #             )
        #             # 고객 할인 금액 추가 누적
        #             discount_amount = item.menu.menu_price * item.current_discount_rate
        #             customer.user_discounted_cost_sum += discount_amount
        #             customer.save()
        #             # 아이템 재고 차감(0으로)
        #             item.item_stock = 0
        #             item.save()
        #             # 해당 시간슬롯 예약됨으로 처리
        #             slot.is_reserved = True
        #             slot.save()
        #             # 중복예약 방지
        #             items_with_stock.remove(item)
        #             # 매장 활성여부 업데이트
        #             store = item.store
        #             store.is_active = store.storeitem_set.filter(
        #                 item_stock__gt=0
        #             ).exists()
        #             store.save()

        # # 고객 좋아요(UserLike) 랜덤 생성
        # for customer in customers:
        #     like_count = random.randint(2, 5)
        #     if stores:  # [방어] stores가 비어있을 때 예외처리
        #         liked_stores = random.sample(stores, min(like_count, len(stores)))
        #         for store in liked_stores:
        #             UserLike.objects.create(user=customer, store=store, is_dummy=True)

        # 매장별 운영시간(StoreOperatingHour) 임의 생성(오픈/마감)
        for store in stores:
            for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
                open_time = random.randint(7, 10)
                close_time = random.randint(18, 23)
                StoreOperatingHour.objects.create(
                    store=store,
                    day_of_week=day,
                    open_time=open_time,
                    close_time=close_time,
                    is_dummy=True,
                )

        self.stdout.write(
            self.style.SUCCESS(
                "✅ 더미데이터 생성 완료 (더미 customer 없음 + 예약 생성 안함 + 현재 할인율 10%)"
            )
        )


# customer 있던 버전은 실행 시 buynow % python manage.py generate_dummy_data --dev --owners 40 --customers 80 --stores 40 --days 10
# 지금은 실행 시 buynow % python manage.py generate_dummy_data --dev --owners 50 --stores 50 --days 10
# 숫자는 상황에 맞게 변경 가능 (실행 전 상의 필수!)
