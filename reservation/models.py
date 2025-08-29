from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class Lounge(models.Model):
    number = models.IntegerField(choices=[(1, '1'), (2, '2')], unique=True)

    def __str__(self):
        return f"Lounge {self.number}"

class Reservation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    lounge = models.ForeignKey(Lounge, on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    end_time   = models.DateTimeField()
    # 신청자 이름 나열(예: "김00, 이00")
    applicant_names = models.CharField(max_length=255, blank=True)

    def is_active(self):
        now = timezone.localtime()
        return self.start_time <= now < self.end_time

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['lounge', 'start_time'],
                name='unique_lounge_timeslot',
            )
        ]

    def __str__(self):
        return f"{self.lounge} {self.start_time:%Y-%m-%d %H:%M}"
