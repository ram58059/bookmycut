from django.urls import path
from . import views

urlpatterns = [
    path('', views.overview, name='dashboard_overview'),
    path('login/', views.dashboard_login, name='dashboard_login'),
    path('services/', views.service_performance, name='dashboard_services'),
    path('services/add/', views.add_service, name='dashboard_add_service'),
    path('services/<int:pk>/edit/', views.edit_service, name='dashboard_edit_service'),
    path('services/<int:pk>/delete/', views.delete_service, name='dashboard_delete_service'),
    path('customers/', views.customer_insights, name='dashboard_customers'),
    path('cancellations/', views.cancellation_analytics, name='dashboard_cancellation'),
    path('utilization/', views.utilization, name='dashboard_utilization'),
    path('orders/', views.orders_dashboard, name='dashboard_orders'),
    path('manage/', views.manage_bookings, name='dashboard_manage_bookings'),
    path('toggle-otp/', views.toggle_otp, name='toggle_otp'),
]
