from django.db import models
from accounts.models import User, BaseModel
from stores.models import Store, StoreItem, StoreSlot

class Reservation(BaseModel):
    reservation_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store_item = models.ForeignKey(StoreItem, on_delete=models.CASCADE)
    reservation_slot = models.ForeignKey(StoreSlot, on_delete=models.CASCADE)
    reservation_cost = models.PositiveIntegerField()
    is_dummy = models.BooleanField(default=False)
    class Meta:
        unique_together = ('user', 'store_item')

class UserLike(BaseModel):
    like_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey(Store, on_delete=models.CASCADE)
    is_dummy = models.BooleanField(default=False)

#TODO 검토필요