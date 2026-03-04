from django.urls import path
from . import views, views_ajax

urlpatterns = [
    # Wizard Steps
    path('gender/', views.GenderSelectionView.as_view(), name='gender_selection'),
    path('services/', views.ServiceListView.as_view(), name='service_list'),
    path('date-time/', views.DateTimeSelectionView.as_view(), name='date_time_selection'),
    path('confirm/', views.BookingConfirmationView.as_view(), name='booking_confirmation'),
    
    # Verification
    path('verify-otp/', views.OTPVerificationView.as_view(), name='otp_verification'),
    path('success/', views.BookingSuccessView.as_view(), name='booking_success'), # New Success
    
    # User Dashboard
    path('orders/', views.OrderListView.as_view(), name='my_orders'),
    path('cancel/<int:booking_id>/', views.CancelBookingView.as_view(), name='cancel_booking'),

    # AJAX Endpoints (Restoring these!)
    path('api/initiate-booking/', views_ajax.InitiateBookingView.as_view(), name='api_initiate_booking'),
    path('api/verify-otp/', views_ajax.VerifyBookingOTPView.as_view(), name='api_verify_otp'),
    path('api/resend-otp/', views_ajax.ResendOTPView.as_view(), name='api_resend_otp'),
]
