from django.contrib import admin
from .models import Lounge, Reservation

@admin.register(Lounge)
class LoungeAdmin(admin.ModelAdmin):
    list_display = ('number',)

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('lounge', 'user', 'start_time', 'end_time')
    list_filter = ('lounge', 'start_time')