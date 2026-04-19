from django.urls import path
from . import views

urlpatterns = [
    path('', views.sales_list, name='sales_list'),
    path('create/', views.sale_create, name='sale_create'),
    path('<int:pk>/', views.sale_detail, name='sale_detail'),
    path('<int:pk>/confirm/', views.sale_confirm, name='sale_confirm'),
    path('<int:pk>/review/', views.sale_review, name='sale_review'),
    path('analytics/', views.sales_analytics, name='sales_analytics'),
    path('debts/', views.debts_list, name='debts_list'),
    path('payment/<int:pharmacy_id>/', views.payment_create, name='payment_create'),
    path('<int:pk>/invoice/', views.invoice_view, name='invoice_view'),
]
