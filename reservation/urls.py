# reservation/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.reservation_page, name='reservation_page'),  # 기본 페이지
    path('cancel/<int:reservation_id>/', views.cancel_reservation, name='cancel_reservation'),
]
