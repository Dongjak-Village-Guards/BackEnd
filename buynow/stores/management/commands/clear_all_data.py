from django.core.management.base import BaseCommand
from accounts.models import User
from stores.models import (
    Store,
    StoreSlot,
    StoreItem,
    StoreMenu,
    StoreMenuSpace,
    StoreSpace,
    StoreOperatingHour,
)
from reservations.models import Reservation, UserLike


class Command(BaseCommand):
    help = "모든 데이터 삭제 (주의: 되돌릴 수 없음!)"

    def handle(self, *args, **options):
        confirm = input("⚠ 모든 데이터가 삭제됩니다. 계속하시겠습니까? (YES 입력) : ")
        if confirm != "YES":
            self.stdout.write(self.style.ERROR("취소됨"))
            return

        Reservation.objects.all().delete()
        UserLike.objects.all().delete()
        StoreOperatingHour.objects.all().delete()
        StoreItem.objects.all().delete()
        StoreSlot.objects.all().delete()
        StoreMenuSpace.objects.all().delete()
        StoreMenu.objects.all().delete()
        StoreSpace.objects.all().delete()
        Store.objects.all().delete()
        User.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("✅ 레코드 제외 모든 데이터 삭제 완료"))

        # 실행 시 python manage.py clear_all_data
