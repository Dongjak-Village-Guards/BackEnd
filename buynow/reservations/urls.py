from django.urls import path
from .views import *

urlpatterns = [
    # 로깅 관련
    path('test-logger/', view_func, name='test_logger'),

    # UserLike api 관련
    path('userlikes/', LikeDetail.as_view(), name = 'userlike'),

    # Reservation api 관련
    path('', ReserveList.as_view(), name = 'make_userlike'),
    path('me/', ReserveMe.as_view(), name = 'my_userlike_list'),
    path('<int:reservation_id>/', ReserveDetail.as_view(), name = 'delete_userlike'),

    # 공급자 api 관련
    path('close/owner/', OwnerClosed.as_view(), name = 'make_slot_closed'),
    path('open/owner/', OwnerOpen.as_view(), name = 'make_slot_open'),
]