from django.urls import path
from . import views

urlpatterns = [
    path("", views.reservation_page, name="reservation_page"),
    path("make_reservation/", views.make_reservation, name="make_reservation"),
    path("cancel/<int:reservation_id>/", views.cancel_reservation, name="cancel_reservation"),
]
