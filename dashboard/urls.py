from django.urls import path
from . import views

urlpatterns = [
    path('', views.overview, name='dashboard_overview'),
    path('login/', views.dashboard_login, name='dashboard_login'),
    path('services/', views.service_performance, name='dashboard_services'),
    path('demand/', views.peak_time, name='dashboard_peak_time'),
    path('customers/', views.customer_insights, name='dashboard_customers'),
    path('cancellations/', views.cancellation_analytics, name='dashboard_cancellation'),
    path('utilization/', views.utilization, name='dashboard_utilization'),
    path('manage/', views.manage_bookings, name='dashboard_manage_bookings'),
]
