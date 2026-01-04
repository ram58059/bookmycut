from django.urls import path
from .views import (
    GenderSelectionView,
    ServiceListView, 
    DateTimeSelectionView, 
    BookingConfirmationView, 
    BookingSuccessView
)

urlpatterns = [
    path('book/gender/', GenderSelectionView.as_view(), name='gender_selection'),
    path('book/services/', ServiceListView.as_view(), name='service_list'),
    path('book/calendar/', DateTimeSelectionView.as_view(), name='date_time_selection'),
    path('book/confirm/', BookingConfirmationView.as_view(), name='booking_confirmation'),
    path('book/success/', BookingSuccessView.as_view(), name='booking_success'),
]
