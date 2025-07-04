from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser, PermissionsMixin, BaseUserManager
)
from django.core.validators import RegexValidator
from django.utils import timezone

class CustomUserManager(BaseUserManager):
    def create_user(self, student_number, name, password=None, **extra_fields):
        if not student_number:
            raise ValueError('학번(student_number)을 반드시 입력해야 합니다.')
        if not name:
            raise ValueError('이름(name)을 반드시 입력해야 합니다.')
        # student_number는 문자열이어야 하고, 5자리 숫자여야 함
        user = self.model(
            student_number=student_number,
            name=name,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, student_number, name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if not extra_fields.get('is_staff'):
            raise ValueError('슈퍼유저는 is_staff=True 이어야 합니다.')
        if not extra_fields.get('is_superuser'):
            raise ValueError('슈퍼유저는 is_superuser=True 이어야 합니다.')

        return self.create_user(student_number, name, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    # 5자리 숫자 검증기
    student_number = models.CharField(
        max_length=5,
        unique=True,
        validators=[RegexValidator(r'^\d{5}$', '학번은 5자리 숫자여야 합니다.')]
    )
    name = models.CharField(max_length=30, help_text='실명을 입력하세요')

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = CustomUserManager()

    # 로그인 시 사용하는 필드로 student_number 지정
    USERNAME_FIELD = 'student_number'
    REQUIRED_FIELDS = ['name']

    def __str__(self):
        return f'{self.student_number} ({self.name})'