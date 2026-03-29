from django.urls import path
from . import views

urlpatterns = [
    path('', views.warehouses_list, name='warehouses_list'),
    path('create/', views.warehouse_create, name='warehouse_create'),
    path('<int:pk>/', views.warehouse_detail, name='warehouse_detail'),
    path('products/', views.products_list, name='products_list'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('stock-in/', views.stock_in, name='stock_in'),
    path('write-off/', views.stock_writeoff, name='stock_writeoff'),
    path('expiring/', views.expiring_report, name='expiring_report'),
    path('movements/', views.movements_list, name='movements_list'),
    path('dora-report/', views.dora_report, name='dora_report'),
    path('dora-import/', views.dora_import, name='dora_import'),
]
