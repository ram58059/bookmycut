from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('hairstyles/', views.hairstyle_gallery, name='hairstyle_gallery'),
]
