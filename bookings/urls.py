from django.urls import path
from .views import (
    GenderSelectionView,
    ServiceListView, 
    DateTimeSelectionView, 
    BookingConfirmationView, 
    BookingSuccessView,
    OTPVerificationView,
    CancelBookingView
)

urlpatterns = [
    path('book/gender/', GenderSelectionView.as_view(), name='gender_selection'),
    path('book/services/', ServiceListView.as_view(), name='service_list'),
    path('book/calendar/', DateTimeSelectionView.as_view(), name='date_time_selection'),
    path('book/confirm/', BookingConfirmationView.as_view(), name='booking_confirmation'),
    path('book/verify-otp/', OTPVerificationView.as_view(), name='otp_verification'),
    path('book/success/', BookingSuccessView.as_view(), name='booking_success'),
    path('book/cancel/<int:booking_id>/', CancelBookingView.as_view(), name='cancel_booking'),
]
