from django.contrib import admin
from .models import Sale, SaleItem, SalesPlan, Invoice, LegalEntity


@admin.register(LegalEntity)
class LegalEntityAdmin(admin.ModelAdmin):
    list_display  = ['name', 'entity_type', 'inn', 'address', 'is_default']
    list_filter   = ['entity_type', 'is_default']
    search_fields = ['name', 'inn']
    fieldsets = [
        (None, {'fields': ['name', 'entity_type', 'is_default']}),
        ('Реквизиты', {'fields': ['address', 'inn', 'certificate', 'phone']}),
        ('Банковские данные', {'fields': ['bank', 'account', 'bik']}),
    ]


class SaleItemInline(admin.TabularInline):
    model        = SaleItem
    extra        = 0
    raw_id_fields = ['batch']
    fields       = ['batch', 'quantity', 'sale_price', 'cost_price']
    readonly_fields = []


class InvoiceInline(admin.StackedInline):
    model = Invoice
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display   = ['pk', 'date', 'pharmacy', 'employee', 'warehouse',
                      'status', 'total_amount', 'total_cost']
    list_filter    = ['status', 'date']
    search_fields  = ['pharmacy__name', 'employee__username']
    raw_id_fields  = ['pharmacy', 'employee', 'warehouse']
    date_hierarchy = 'date'
    inlines        = [SaleItemInline, InvoiceInline]


@admin.register(SalesPlan)
class SalesPlanAdmin(admin.ModelAdmin):
    list_display  = ['employee', 'month', 'year', 'plan_amount']
    list_filter   = ['year', 'month']
    raw_id_fields = ['employee']


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display  = ['invoice_number', 'sale', 'date', 'issued_by']
    search_fields = ['invoice_number']
    raw_id_fields = ['sale', 'issued_by']
