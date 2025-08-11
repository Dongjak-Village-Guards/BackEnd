import uuid
from django.db import models

# Create your models here.
# 추상 클래스 정의
class BaseModel(models.Model): # models.Model을 상속받음
    created_at = models.DateTimeField(auto_now_add=True) # 객체를 생성할 때 날짜와 시간 저장
    updated_at = models.DateTimeField(auto_now=True) # 객체를 저장할 때 날짜와 시간 갱신

    class Meta:
        abstract = True

# User 모델 정의
class User(BaseModel):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('customer', 'Customer'),
        ('owner', 'Owner'),
    )

    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_email = models.EmailField(unique = True) # 'null=True' 이거는 넣을지말지 잘 모르겠어서 일단 제외
    user_image_url = models.TextField(blank = True)
    user_password = models.CharField(max_length=10, default = "") # 나중에 해시 처리해서 DB에 저장해야 함. (Abstract 그걸로 바꾸면 해시 처리 해주는게 내장되어 있다고 함)
    user_role = models.CharField(max_length = 20, choices = ROLE_CHOICES, default = 'customer')
    user_address = models.CharField(blank = True, max_length = 100) # 'null=True' 이거는 넣을지말지 잘 모르겠어서 일단 제외
    user_discounted_cost_sum = models.IntegerField(default = 0)

    def __str__(self):
        return f"{self.email} ({self.role})"
