from django.core.management.base import BaseCommand, CommandError
from pricing.models import MenuPricingParam
from records.models import ItemRecord
from reservations.models import Reservation, UserLike
from stores.models import (
    Store,
    StoreSpace,
    StoreMenu,
    StoreMenuSpace,
    StoreOperatingHour,
    StoreItem,
    StoreSlot,
)
from accounts.models import User
from stores.data.dongjak_addresses import dongjak_addresses
from stores.data.dummy_store_templates import store_templates
from pricing.utils import (
    calculate_time_offset_idx,
    create_item_record,
    safe_create_item_record,
)
from datetime import datetime, timedelta
import random
from faker import Faker
from django.utils import timezone


class Command(BaseCommand):
    help = "전체 더미데이터 생성 (ItemRecord 제외) - 배치 처리 50개 단위 적용"

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

    def _batch_delete(self, queryset, batch_size=50):
        while True:
            ids = list(queryset.values_list("pk", flat=True)[:batch_size])
            if not ids:
                break
            queryset.model.objects.filter(pk__in=ids).delete()

    def handle(self, *args, **options):
        if not options["dev"] and not options["prod"]:
            raise CommandError("--dev 또는 --prod 옵션 중 하나를 지정하세요.")

        if options["prod"]:
            self.stdout.write(self.style.WARNING("⚠ 운영 DB에서 실행됩니다."))
            confirm = input("정말 실행하시겠습니까? (YES 입력) : ")
            if confirm != "YES":
                self.stdout.write(self.style.ERROR("취소됨"))
                return

        faker = Faker("ko_KR")
        # start_date = datetime.today().date() - timedelta(days=7)
        start_date = timezone.localtime().date() - timedelta(days=7)
        days = options["days"]
        hours = options["hours"]
        batch_size = 20  # 배치 크기 50으로 설정

        # 기존 데이터 모두 배치 삭제
        if not options["skip_delete"]:
            self.stdout.write("기존 데이터 전부 삭제 중...")
            self._batch_delete(Reservation.objects.all(), batch_size)
            self._batch_delete(ItemRecord.objects.all(), batch_size)
            self._batch_delete(MenuPricingParam.objects.all(), batch_size)
            self._batch_delete(UserLike.objects.all(), batch_size)
            self._batch_delete(StoreOperatingHour.objects.all(), batch_size)
            self._batch_delete(StoreItem.objects.all(), batch_size)
            self._batch_delete(StoreSlot.objects.all(), batch_size)
            self._batch_delete(StoreMenuSpace.objects.all(), batch_size)
            self._batch_delete(StoreMenu.objects.all(), batch_size)
            self._batch_delete(StoreSpace.objects.all(), batch_size)
            self._batch_delete(Store.objects.all(), batch_size)
            self._batch_delete(User.objects.all(), batch_size)
            self.stdout.write("기존 데이터 삭제 완료")

        # --- 주소 & 템플릿 준비 ---
        address_pool = random.sample(dongjak_addresses, len(dongjak_addresses))
        selected_templates = random.sample(store_templates, options["stores"])

        def safe_pop_address():
            return address_pool.pop() if address_pool else faker.address()

        # --- Users 생성 ---
        owners = [
            User(
                user_email=faker.unique.email(),
                user_role="owner",
                user_address=safe_pop_address(),
                user_discounted_cost_sum=0,
                is_dummy=True,
            )
            for _ in range(options["owners"])
        ]
        customers = [
            User(
                user_email=faker.unique.email(),
                user_role="customer",
                user_address=safe_pop_address(),
                user_discounted_cost_sum=0,
                is_dummy=True,
            )
            for _ in range(options["customers"])
        ]

        # 배치로 bulk_create 실행
        def batch_create(model, objects, batch_size):
            for i in range(0, len(objects), batch_size):
                model.objects.bulk_create(objects[i : i + batch_size])

        batch_create(User, owners + customers, batch_size)
        self.stdout.write(
            self.style.NOTICE(
                f"Users 생성 완료: 점주 {len(owners)}명, 고객 {len(customers)}명"
            )
        )

        # (중요!) DB에서 owners, customers를 다시 가져와야 함 (PK가 할당된 상태로)
        owners = list(User.objects.filter(user_role="owner", is_dummy=True))
        customers = list(User.objects.filter(user_role="customer", is_dummy=True))

        # --- Store 생성 ---
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
                store = Store(
                    store_name=template["store_name"],
                    store_owner=owner,
                    store_category=template["category"],
                    store_description=template["description"],
                    store_address=safe_pop_address(),
                    is_dummy=True,
                    store_image_url=template["image_url"],
                    is_active=True,
                )
                stores.append(store)
                store_template_pairs.append((store, template))

        batch_create(Store, stores, batch_size)
        self.stdout.write(
            self.style.NOTICE(f"Stores 생성 완료: {len(stores)}개 매장 생성")
        )
        # Store fresh 쿼리
        stores = list(Store.objects.filter(is_dummy=True))
        # 매핑: store_name → Store 객체
        store_name_to_store = {store.store_name: store for store in stores}
        # 매핑: store_name → template 딕셔너리 생성
        store_name_to_template = {s.store_name: t for s, t in store_template_pairs}

        store_menus = []
        store_spaces = []
        store_menu_spaces = []

        # StoreMenu, StoreSpace 생성: fresh Store 기준 & store_name으로 template 찾기
        for store_name, fresh_store in store_name_to_store.items():
            template = store_name_to_template.get(store_name)
            if not template:
                continue  # template 없으면 건너뜀

            for menu_t in template["menus"]:
                store_menus.append(
                    StoreMenu(
                        store=fresh_store,
                        menu_name=menu_t["menu_name"],
                        menu_image_url=menu_t["image_url"],
                        menu_cost_price=menu_t["cost_price"],
                        menu_price=menu_t["price"],
                        dp_weight=0.0,
                        is_dummy=True,
                    )
                )

            for space_t in template["spaces"]:
                store_spaces.append(
                    StoreSpace(
                        store=fresh_store,
                        space_name=space_t["space_name"],
                        space_image_url=space_t["image_url"],
                        space_description=space_t["description"],
                        is_dummy=True,
                    )
                )

        batch_create(StoreMenu, store_menus, batch_size)
        batch_create(StoreSpace, store_spaces, batch_size)

        # fresh 쿼리 후 store_menu_map, store_space_map 생성
        store_menus = list(StoreMenu.objects.filter(store__in=stores))
        store_spaces = list(StoreSpace.objects.filter(store__in=stores))
        store_menu_map = {(m.store_id, m.menu_name): m for m in store_menus}
        store_space_map = {(s.store_id, s.space_name): s for s in store_spaces}

        self.stdout.write(f"store_template_pairs 개수: {len(store_template_pairs)}")
        self.stdout.write(f"store_spaces 개수: {len(store_spaces)}")
        self.stdout.write(f"store_menu_map 개수: {len(store_menu_map)}")

        # StoreMenuSpace 생성
        for store_name, fresh_store in store_name_to_store.items():
            template = store_name_to_template.get(store_name)
            if not template:
                continue

            space_objs = [
                space
                for space in store_spaces
                if space.store_id == fresh_store.store_id
            ]
            self.stdout.write(f"{fresh_store.store_name} - 공간개수: {len(space_objs)}")

            for space in space_objs:
                menu_names = [m["menu_name"] for m in template["menus"]]
                menus_for_space = [
                    store_menu_map.get((fresh_store.store_id, mn))
                    for mn in menu_names
                    if store_menu_map.get((fresh_store.store_id, mn))
                ]
                self.stdout.write(
                    f"공간 {space.space_name} - 연관 메뉴개수: {len(menus_for_space)}"
                )

                for menu in random.sample(
                    menus_for_space,
                    min(len(menus_for_space), random.randint(1, len(menus_for_space))),
                ):
                    store_menu_spaces.append(
                        StoreMenuSpace(menu=menu, space=space, is_dummy=True)
                    )

        self.stdout.write(f"store_menu_spaces 개수: {len(store_menu_spaces)}")
        batch_create(StoreMenuSpace, store_menu_spaces, batch_size)

        self.stdout.write(
            self.style.NOTICE("StoreMenu, StoreSpace, StoreMenuSpace 생성 완료")
        )

        # --- StoreItem 생성 배치 처리 ---
        records_to_create = []

        # 사전에 store_name을 key로 한 매핑 생성 (handle 메서드 초반에 추가)
        store_name_to_template = {s.store_name: t for s, t in store_template_pairs}

        def find_max_discount(menu):
            template = store_name_to_template.get(menu.store.store_name)
            if not template:
                return 0.3
            for m in template.get("menus", []):
                if m.get("menu_name") == menu.menu_name:
                    # 15% ~ 50% 사이 랜덤 할인율 생성
                    return round(random.uniform(0.15, 0.5), 2)
            return 0.3

        for sms in StoreMenuSpace.objects.all():
            menu = sms.menu
            max_discount_rate = find_max_discount(menu)

            for day_offset in range(days):
                date = start_date + timedelta(days=day_offset)
                for hour in hours:
                    stock = 1 if random.random() < 0.5 else 0
                    record = StoreItem(
                        menu=menu,
                        space=sms.space,
                        store=menu.store,
                        item_reservation_date=date,
                        item_reservation_day=date.strftime("%a"),
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

        if records_to_create:
            StoreItem.objects.bulk_create(records_to_create)
            self.stdout.write(
                self.style.NOTICE(
                    f"StoreItem 생성 완료, 총 개수: {len(records_to_create)}"
                )
            )
        else:
            self.stdout.write(self.style.NOTICE("StoreItem 생성 완료"))

        # --- StoreSlot 생성 배치 처리 ---
        records_to_create = []
        for space in StoreSpace.objects.all():
            for day_offset in range(days):
                date = start_date + timedelta(days=day_offset)
                for hour in hours:
                    record = StoreSlot(
                        space=space,
                        slot_reservation_date=date,
                        slot_reservation_time=hour,
                        is_reserved=False,
                        is_dummy=True,
                    )
                    records_to_create.append(record)
                    if len(records_to_create) >= batch_size:
                        StoreSlot.objects.bulk_create(records_to_create)
                        self.stdout.write(
                            self.style.NOTICE(
                                f"StoreSlot 생성 진행: {len(records_to_create)}개 생성"
                            )
                        )
                        records_to_create.clear()
        if records_to_create:
            StoreSlot.objects.bulk_create(records_to_create)
            self.stdout.write(
                self.style.NOTICE(
                    f"StoreSlot 생성 완료, 총 개수: {len(records_to_create)}"
                )
            )
        else:
            self.stdout.write(self.style.NOTICE("StoreSlot 생성 완료"))

        # --- 예약 생성 ---
        # items_with_stock = list(StoreItem.objects.filter(item_stock=1))
        # today = date.today()
        # dummy_start_date = today - timedelta(days=6)
        # dummy_end_date = today - timedelta(days=1)
        today = timezone.localtime().date()
        dummy_start_date = today - timedelta(days=6)
        dummy_end_date = today - timedelta(days=1)

        items_with_stock = list(
            StoreItem.objects.filter(
                item_stock=1,
                item_reservation_date__gte=dummy_start_date,
                item_reservation_date__lte=dummy_end_date,
            )
        )
        random.shuffle(items_with_stock)

        for idx, customer in enumerate(customers):
            for _ in range(random.randint(1, 3)):
                available_items = [
                    item for item in items_with_stock if item.item_stock == 1
                ]
                if not available_items:
                    break
                item = random.choice(available_items)
                slot = StoreSlot.objects.filter(
                    space=item.space,
                    slot_reservation_date=item.item_reservation_date,
                    slot_reservation_time=item.item_reservation_time,
                    is_reserved=False,
                ).first()
                if slot:
                    discounted_price = round(
                        item.menu.menu_price * (1 - item.current_discount_rate)
                    )
                    Reservation.objects.create(
                        user=customer,
                        store_item=item,
                        reservation_slot=slot,
                        reservation_cost=discounted_price,
                        is_dummy=True,
                    )

                    safe_create_item_record(item, sold=1, is_dummy_flag=True)

                    discount_amount = item.menu.menu_price * item.current_discount_rate
                    customer.user_discounted_cost_sum += discount_amount
                    customer.save()
                    item.item_stock = 0
                    item.save()
                    slot.is_reserved = True
                    slot.save()
                    items_with_stock.remove(item)
                    # store = item.store
                    # store.is_active = store.storeitem_set.filter(
                    #     item_stock__gt=0
                    # ).exists()
                    # store.save()

            if (idx + 1) % 10 == 0:
                self.stdout.write(
                    self.style.NOTICE(
                        f"예약 생성 진행: 고객 {idx + 1}/{len(customers)} 완료"
                    )
                )

        self.stdout.write(self.style.NOTICE("예약 생성 완료"))
        # 예약 생성 완료 후 store.is_active 일괄 업데이트
        for store in stores:
            store.is_active = store.storeitem_set.filter(item_stock__gt=0).exists()
            store.save()

        # --- 미판매 재고에 대한 기록 ---
        count = 0
        for item in StoreItem.objects.filter(item_stock=1, is_dummy=True):
            safe_create_item_record(item, sold=0, is_dummy_flag=True)
            count += 1
            if count % 100 == 0:
                self.stdout.write(
                    self.style.NOTICE(f"미판매 재고 기록 생성 진행: {count}개 완료")
                )

        self.stdout.write(
            self.style.NOTICE(f"미판매 재고 기록 생성 완료, 총 {count}개")
        )

        # --- UserLike 생성 ---
        records_to_create = []
        for customer in customers:
            like_count = random.randint(2, 5)
            if stores:
                liked_stores = random.sample(stores, min(like_count, len(stores)))
                for store in liked_stores:
                    record = UserLike(user=customer, store=store, is_dummy=True)
                    records_to_create.append(record)
                    if len(records_to_create) >= batch_size:
                        UserLike.objects.bulk_create(records_to_create)
                        self.stdout.write(
                            self.style.NOTICE(
                                f"UserLike 생성 진행: {len(records_to_create)}개 생성"
                            )
                        )
                        records_to_create.clear()
        if records_to_create:
            UserLike.objects.bulk_create(records_to_create)
            self.stdout.write(
                self.style.NOTICE(
                    f"UserLike 생성 완료, 총 개수: {len(records_to_create)}"
                )
            )
        else:
            self.stdout.write(self.style.NOTICE("UserLike 생성 완료"))

        # --- StoreOperatingHour 생성 ---
        records_to_create = []
        for store in stores:
            for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
                open_time = random.randint(7, 10)
                close_time = random.randint(18, 23)
                record = StoreOperatingHour(
                    store=store,
                    day_of_week=day,
                    open_time=open_time,
                    close_time=close_time,
                    is_dummy=True,
                )
                records_to_create.append(record)
                if len(records_to_create) >= batch_size:
                    StoreOperatingHour.objects.bulk_create(records_to_create)
                    self.stdout.write(
                        self.style.NOTICE(
                            f"StoreOperatingHour 생성 진행: {len(records_to_create)}개 생성"
                        )
                    )
                    records_to_create.clear()

        if records_to_create:
            StoreOperatingHour.objects.bulk_create(records_to_create)
            self.stdout.write(
                self.style.NOTICE(
                    f"StoreOperatingHour 생성 완료, 총 개수: {len(records_to_create)}"
                )
            )
        else:
            self.stdout.write(self.style.NOTICE("StoreOperatingHour 생성 완료"))

        self.stdout.write(self.style.SUCCESS("✅ 더미데이터 생성 완료"))
