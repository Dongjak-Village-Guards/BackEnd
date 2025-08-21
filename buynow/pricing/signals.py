from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from reservations.models import Reservation
from pricing.utils import safe_create_item_record  # safe 함수 import로 변경


@receiver(post_save, sender=Reservation)
def reservation_created_handler(sender, instance, created, **kwargs):
    if created:
        safe_create_item_record(instance.store_item, sold=1, is_dummy_flag=False)


@receiver(post_delete, sender=Reservation)
def reservation_deleted_handler(sender, instance, **kwargs):
    # 더미데이터 삭제 시 무한 루프 방지를 위해 조건 추가
    if instance.is_dummy:
        return
    safe_create_item_record(instance.store_item, sold=0, is_dummy_flag=False)
