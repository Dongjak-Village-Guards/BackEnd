from django.db.models.signals import post_save
from django.dispatch import receiver
from reservations.models import Reservation
from pricing.utils import record_event_and_update_discount


@receiver(post_save, sender=Reservation)
def reservation_created_handler(sender, instance, created, **kwargs):
    if created:
        record_event_and_update_discount(
            instance.store_item, sold=1, is_dummy_flag=False
        )
