from django.urls import path
from .views import *

urlpatterns = [
    path('login/', GoogleLoginAPIView.as_view(), name = 'login'),
    path('login/admin/', AdminLoginAPIView.as_view(), name = 'admin_login'),
    path('login/refresh/', TokenRefreshAPIView.as_view(), name = 'new_access_token')
]