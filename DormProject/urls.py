from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # ── 예약 앱은 루트 그대로 두고 ──
    path('', include('reservation.urls')),

    # ── 로그인/로그아웃은 루트 바로 아래에 두기 ──
    path('', include('login.urls')),                  # login/urls.py 의 login/ 와 logout/ 매핑
    path('', include('django.contrib.auth.urls')),          # 기본 auth 뷰 (password_change 등)도 / 로직 하위에
]
