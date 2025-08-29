from django.urls import path
from . import views

app_name = "reservation"

urlpatterns = [
    path("", views.schedule, name="schedule"),
    path("reserve-slot/<int:number>/<str:start_key>/", views.reserve_slot, name="reserve_slot"),
]
