from django.urls import path
from .views import google_login

urlpatterns = [
    path('login/', google_login, name = 'login'),
]