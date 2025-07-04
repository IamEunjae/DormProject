from django.urls import path
from . import views

app_name = 'reservation'

urlpatterns = [
    path('', views.lounge_list, name='lounge_list'),
    path('reserve/<int:number>/', views.reserve_lounge, name='reserve_lounge'),
]