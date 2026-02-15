from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('hairstyles/', views.hairstyle_gallery, name='hairstyle_gallery'),
    path('T&C/', views.terms, name='terms'),
    path('privacy_policy/', views.privacy, name='privacy'),
    path('refund_policy/', views.refund, name='refund'),
]
