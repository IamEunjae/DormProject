# reservation/admin.py
from django.contrib import admin
from .models import Lounge, Reservation

@admin.register(Lounge)
class LoungeAdmin(admin.ModelAdmin):
    list_display = ('number',)
    ordering = ('number',)

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('lounge','start_time','end_time','user','applicant_names')
    list_filter = ('lounge__number','start_time')
    ordering = ('-start_time',)
