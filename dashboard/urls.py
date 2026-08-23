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
    path('offers/', views.offers_list, name='dashboard_offers'),
    path('offers/add/', views.add_coupon, name='dashboard_add_coupon'),
    path('offers/customers/search/', views.search_coupon_customers, name='dashboard_search_coupon_customers'),
    path('offers/<int:pk>/edit/', views.edit_coupon, name='dashboard_edit_coupon'),
    path('offers/<int:pk>/delete/', views.delete_coupon, name='dashboard_delete_coupon'),
    path('combo-services/', views.combo_services_list, name='dashboard_combo_services'),
    path('combo-services/add/', views.add_combo_service, name='dashboard_add_combo_service'),
    path('combo-services/<int:pk>/edit/', views.edit_combo_service, name='dashboard_edit_combo_service'),
    path('combo-services/<int:pk>/delete/', views.delete_combo_service, name='dashboard_delete_combo_service'),
    path('combo-services/<int:pk>/reorder/<str:direction>/', views.reorder_combo_service, name='dashboard_reorder_combo_service'),
    path('combo-services/<int:pk>/toggle/', views.toggle_combo_service, name='dashboard_toggle_combo_service'),
    path('customers/', views.customer_insights, name='dashboard_customers'),
    path('orders/', views.orders_dashboard, name='dashboard_orders'),
    path('orders/book/', admin_booking.admin_book_slot, name='dashboard_book_slot'),
    path('settings/business-phone/', views.update_business_phone, name='dashboard_update_business_phone'),
    path('manage/', views.manage_bookings, name='dashboard_manage_bookings'),
    path('finance/', finance_views.finance_dashboard, name='dashboard_finance'),
    path('toggle-otp/', views.toggle_otp, name='toggle_otp'),
]
