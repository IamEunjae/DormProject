from django.urls import path
from django.contrib.auth import views as auth_views

app_name = 'login'

urlpatterns = [
    # 로그인
    path('login/', auth_views.LoginView.as_view(template_name='login/login.html'), name='login'),
    # 로그아웃 (로그아웃 후 login 페이지로)
    path('logout/', auth_views.LogoutView.as_view(next_page='login:login'), name='logout'),
]
