from django.db import models
from accounts.models import BaseModel

class ItemRecord(BaseModel):
    record_id = models.AutoField(primary_key=True)
    store_item_id = models.IntegerField()  # 참조 아님
    record_reservation_time = models.PositiveSmallIntegerField() #아이템 시작시간
    time_offset_idx = models.IntegerField() #시작 시간까지 남은 10분 단위 인덱스 0~18
    record_stock = models.IntegerField() #당시 재고 0 또는 1
    record_item_price = models.PositiveIntegerField() #당시 정가(<- 정가가 바뀌지 않는 한 고정)
    record_discount_rate = models.FloatField() #당시 할인율
    is_dummy = models.BooleanField(default=False)
    class Meta:
        unique_together = ('store_item_id', 'record_reservation_time', 'time_offset_idx')
    
    #TODO 검토필요!