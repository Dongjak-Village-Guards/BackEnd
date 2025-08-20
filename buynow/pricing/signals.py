from django.db.models.signals import post_save
from django.db.models.signals import post_delete
from django.dispatch import receiver
from reservations.models import Reservation
from pricing.utils import create_item_record


@receiver(post_save, sender=Reservation)
def reservation_created_handler(sender, instance, created, **kwargs):
    if created:
        create_item_record(instance.store_item, sold=1, is_dummy_flag=False)


@receiver(post_delete, sender=Reservation)
def reservation_deleted_handler(sender, instance, **kwargs):
    create_item_record(instance.store_item, sold=0, is_dummy_flag=False)
