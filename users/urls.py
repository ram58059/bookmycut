from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.PhoneLoginView.as_view(), name='login'),
    path('verify-otp/', views.VerifyLoginOTPView.as_view(), name='verify_login_otp'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
]
