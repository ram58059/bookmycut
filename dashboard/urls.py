from django.urls import path
from . import views
from . import admin_booking
from . import finance_views

urlpatterns = [
    path('', views.overview, name='dashboard_overview'),
    path('reports/<slug:report>/', views.overview_report, name='dashboard_report'),
    path('login/', views.dashboard_login, name='dashboard_login'),
    path('services/', views.service_performance, name='dashboard_services'),
    path('services/add/', views.add_service, name='dashboard_add_service'),
    path('services/<int:pk>/edit/', views.edit_service, name='dashboard_edit_service'),
    path('services/<int:pk>/delete/', views.delete_service, name='dashboard_delete_service'),
    path('customers/', views.customer_insights, name='dashboard_customers'),
    path('orders/', views.orders_dashboard, name='dashboard_orders'),
    path('orders/book/', admin_booking.admin_book_slot, name='dashboard_book_slot'),
    path('settings/business-phone/', views.update_business_phone, name='dashboard_update_business_phone'),
    path('manage/', views.manage_bookings, name='dashboard_manage_bookings'),
    path('finance/', finance_views.finance_dashboard, name='dashboard_finance'),
    path('toggle-otp/', views.toggle_otp, name='toggle_otp'),
]
