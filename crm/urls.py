from django.urls import path
from . import views

urlpatterns = [
    path('doctors/', views.doctors_list, name='doctors_list'),
    path('doctors/create/', views.doctor_create, name='doctor_create'),
    path('doctors/<int:pk>/', views.doctor_detail, name='doctor_detail'),
    path('pharmacies/', views.pharmacies_list, name='pharmacies_list'),
    path('pharmacies/create/', views.pharmacy_create, name='pharmacy_create'),
    path('pharmacies/<int:pk>/', views.pharmacy_detail, name='pharmacy_detail'),
    path('visits/', views.visits_list, name='visits_list'),
    path('visits/create/', views.visit_create, name='visit_create'),
    path('visits/<int:pk>/', views.visit_detail, name='visit_detail'),
    path('visits/<int:pk>/complete/', views.visit_complete, name='visit_complete'),
]
