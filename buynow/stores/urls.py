from django.urls import path
from .views import StoreListView

urlpatterns = [
    path('', StoreListView.as_view(), name='store-list'),  # GET /v1/stores/
]