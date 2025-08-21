from django.db import models
from accounts.models import User, BaseModel


class Store(BaseModel):
    CATEGORY_CHOICES = (
        ("미용실", "미용실"),
        ("네일샵", "네일샵"),
        ("스터디카페", "스터디카페"),
        ("PT/필라테스", "PT/필라테스"),
        ("스포츠시설", "스포츠시설"),
        ("연습실/합주실", "연습실/합주실"),
        ("사진 스튜디오", "사진 스튜디오"),
    )
    store_id = models.AutoField(primary_key=True)
    store_name = models.CharField(max_length=100)
    store_owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="stores"
    )
    store_category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    store_description = models.TextField(blank=True)
    store_address = models.CharField(max_length=200)
    store_image_url = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_dummy = models.BooleanField(default=False)


class StoreSpace(BaseModel):
    space_id = models.AutoField(primary_key=True)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="spaces")
    space_name = models.CharField(max_length=100)
    space_image_url = models.TextField(blank=True)
    space_description = models.TextField(blank=True)
    is_dummy = models.BooleanField(default=False)  # 더미데이터 여부 표시


class StoreMenu(BaseModel):
    menu_id = models.AutoField(primary_key=True)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="menus")
    menu_name = models.CharField(max_length=100)
    menu_image_url = models.TextField(blank=True)
    menu_cost_price = models.PositiveIntegerField()  # 원가
    menu_price = models.PositiveIntegerField()  # 정가
    dp_weight = models.FloatField(default=0.0)  # 가중치
    is_dummy = models.BooleanField(default=False)


class StoreMenuSpace(BaseModel):
    sms_id = models.AutoField(primary_key=True)
    menu = models.ForeignKey(StoreMenu, on_delete=models.CASCADE)
    space = models.ForeignKey(StoreSpace, on_delete=models.CASCADE)
    is_dummy = models.BooleanField(default=False)

    class Meta:
        unique_together = ("menu", "space")


class StoreOperatingHour(BaseModel):
    DAY_CHOICES = [
        ("Mon", "월"),
        ("Tue", "화"),
        ("Wed", "수"),
        ("Thu", "목"),
        ("Fri", "금"),
        ("Sat", "토"),
        ("Sun", "일"),
    ]
    operating_hour_id = models.AutoField(primary_key=True)
    store = models.ForeignKey(Store, on_delete=models.CASCADE)
    day_of_week = models.CharField(max_length=10, choices=DAY_CHOICES)
    open_time = models.PositiveSmallIntegerField()
    close_time = models.PositiveSmallIntegerField()
    is_dummy = models.BooleanField(default=False)

    class Meta:
        unique_together = ("store", "day_of_week")


class StoreItem(BaseModel):
    item_id = models.AutoField(primary_key=True)
    menu = models.ForeignKey(StoreMenu, on_delete=models.CASCADE)
    space = models.ForeignKey(StoreSpace, on_delete=models.CASCADE)
    store = models.ForeignKey(Store, on_delete=models.CASCADE)
    item_reservation_date = models.DateField()
    item_reservation_day = models.CharField(max_length=10)
    item_reservation_time = models.PositiveSmallIntegerField()  # 0~23
    item_stock = models.IntegerField(default=1)  # 0 또는 1
    current_discount_rate = models.FloatField(default=0.0)
    max_discount_rate = models.FloatField(default=0.3)
    is_dummy = models.BooleanField(default=False)

    class Meta:
        unique_together = (
            "menu",
            "space",
            "item_reservation_date",
            "item_reservation_day",
            "item_reservation_time",
        )


class StoreSlot(BaseModel):
    slot_id = models.AutoField(primary_key=True)
    space = models.ForeignKey(StoreSpace, on_delete=models.CASCADE)
    slot_reservation_date = models.DateField()
    slot_reservation_time = models.PositiveSmallIntegerField()
    is_reserved = models.BooleanField(default=False)
    is_dummy = models.BooleanField(default=False)

    class Meta:
        unique_together = ("space", "slot_reservation_date", "slot_reservation_time")
