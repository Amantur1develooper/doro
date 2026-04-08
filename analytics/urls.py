from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('my/', views.my_analytics, name='my_analytics'),
    path('employees/', views.employee_report, name='employee_report'),
]
