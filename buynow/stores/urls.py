from django.urls import path
from .views import StoreListView
from .views import NumOfSpacesView

urlpatterns = [
    path("", StoreListView.as_view(), name="store-list"),  # GET /v1/stores/
    path(
        "<int:store_id>/", NumOfSpacesView.as_view(), name="num-of-spaces"
    ),  # GET /v1/stores/<store_id>/
]
