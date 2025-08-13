from django.urls import path
from .views import *

urlpatterns = [
    # 로그인 & 토큰 관련
    path('login/', GoogleLoginAPIView.as_view(), name = 'login'),
    path('login/admin/', AdminLoginAPIView.as_view(), name = 'admin_login'),
    #path('login/refresh/', TokenRefreshAPIView.as_view(), name = 'new_access_token'),

    # User api 관련
    path('user/', UserList.as_view(), name = 'user_list')
]