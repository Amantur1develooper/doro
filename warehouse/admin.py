from django.contrib import admin
from .models import Warehouse, ProductCategory, Product, Batch, StockMovement


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display  = ['name', 'address', 'manager']
    search_fields = ['name', 'address']
    raw_id_fields = ['manager']


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display  = ['name']
    search_fields = ['name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display   = ['name', 'category', 'sku', 'unit',
                      'purchase_price', 'cost_price', 'sale_price']
    list_filter    = ['category']
    search_fields  = ['name', 'international_name', 'sku', 'manufacturer']
    list_editable  = ['purchase_price', 'cost_price', 'sale_price']


class BatchInline(admin.TabularInline):
    model  = Batch
    extra  = 0
    fields = ['batch_number', 'warehouse', 'quantity', 'expiry_date', 'purchase_price']


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display   = ['product', 'batch_number', 'warehouse',
                      'quantity', 'expiry_date', 'received_date']
    list_filter    = ['warehouse', 'expiry_date']
    search_fields  = ['product__name', 'batch_number']
    raw_id_fields  = ['product', 'warehouse']
    date_hierarchy = 'expiry_date'


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display   = ['date', 'movement_type', 'batch', 'quantity',
                      'price', 'employee', 'notes']
    list_filter    = ['movement_type', 'date']
    search_fields  = ['batch__product__name', 'notes']
    raw_id_fields  = ['batch', 'employee', 'warehouse_from', 'warehouse_to']
    date_hierarchy = 'date'
