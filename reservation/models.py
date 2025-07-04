from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

class Lounge(models.Model):
    LOUNGE_CHOICES = (
        (1, 'Lounge 1'),
        (2, 'Lounge 2'),
    )
    number = models.IntegerField(choices=LOUNGE_CHOICES, unique=True)

    def __str__(self):
        return f"Lounge {self.number}"

class Reservation(models.Model):
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    lounge = models.ForeignKey(Lounge, on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    # Group participants
    participants = models.ManyToManyField(get_user_model(), related_name='reservations', blank=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Ensure creator is in participants
        self.participants.add(self.user)

    def is_active(self):
        now = timezone.localtime()
        return self.start_time <= now < self.end_time

    def __str__(self):
        return f"{self.lounge} reserved by {self.user}"