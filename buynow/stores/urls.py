from django.urls import path
from .views import StoreListView
from .views import NumOfSpacesView
from .views import StoreSpacesDetailView
from .views import StoreSpaceDetailView
from .views import StoreSingleSpaceDetailView

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
    path(
        "spaces/<int:space_id>/details/",
        StoreSpaceDetailView.as_view(),
        name="store-space-details",
    ),  # GET /v1/stores/spaces/<space_id>/details/
    path(
        "<int:store_id>/menus/",
        StoreSingleSpaceDetailView.as_view(),
        name="store-single-space-detail",
    ),  # GET /v1/stores/<store_id>/menus/
]
