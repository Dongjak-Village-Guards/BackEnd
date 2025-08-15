from django.urls import path
from .views import StoreListView
from .views import NumOfSpacesView
from .views import StoreSpacesDetailView

urlpatterns = [
    path("", StoreListView.as_view(), name="store-list"),  # GET /v1/stores/
    path(
        "<int:store_id>/", NumOfSpacesView.as_view(), name="num-of-spaces"
    ),  # GET /v1/stores/<store_id>/
    path(
        "<int:store_id>/spaces/",
        StoreSpacesDetailView.as_view(),
        name="store-spaces-detail",
    ),  # GET /v1/stores/<store_id>/spaces/
]
