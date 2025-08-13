from django.urls import path
from .views import GoogleLoginAPIView, AdminLoginAPIView

urlpatterns = [
    path('login/', GoogleLoginAPIView.as_view(), name = 'login'),
    path('login/admin/', AdminLoginAPIView.as_view(), name = 'admin_login')
]