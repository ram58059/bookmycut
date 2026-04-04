from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.PhoneLoginView.as_view(), name='login'),
    path('verify-otp/', views.VerifyLoginOTPView.as_view(), name='verify_login_otp'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('ajax-login/', views.AJAXLoginInitiateView.as_view(), name='ajax_login'),
    path('ajax-verify/', views.AJAXLoginVerifyView.as_view(), name='ajax_verify'),
]
