# from django.core.management.base import BaseCommand
# from records.models import ItemRecord
# from stores.models import StoreItem

# class Command(BaseCommand):
#     help = "기존 StoreItem 데이터 기반 ItemRecord 생성"

#     def add_arguments(self, parser):
#         parser.add_argument('--offsets', nargs='+', type=int, default=[0,3,6])
#         parser.add_argument('--clear', action='store_true')

#     def handle(self, *args, **options):
#         if options['clear']:
#             ItemRecord.objects.all().delete()
#             self.stdout.write(self.style.WARNING("기존 ItemRecord 데이터 삭제 완료"))

#         created_count = 0
#         for item in StoreItem.objects.select_related('menu').filter(item_stock=1):
#             for idx in options['offsets']:
#                 ItemRecord.objects.create(
#                     store_item_id=item.id,
#                     record_reservation_time=item.item_reservation_time,
#                     time_offset_idx=idx,
#                     record_stock=item.item_stock,
#                     record_item_price=item.menu.menu_price,
#                     record_discount_rate=item.current_discount_rate
#                 )
#                 created_count += 1

#         self.stdout.write(self.style.SUCCESS(f"✅ {created_count}개의 ItemRecord 생성 완료"))
