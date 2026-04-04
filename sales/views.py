from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count
from django.utils import timezone
from .models import Sale, SaleItem, SalesPlan, Invoice, Payment
from crm.models import Pharmacy
from warehouse.models import Warehouse, Batch, StockMovement
from accounts.models import User
import json


@login_required
def sales_list(request):
    sales = Sale.objects.select_related('pharmacy', 'employee', 'warehouse')
    emp_id = request.GET.get('emp')
    status = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if request.user.role == 'med_rep':
        sales = sales.filter(employee=request.user)
    elif emp_id:
        sales = sales.filter(employee_id=emp_id)
    if status:
        sales = sales.filter(status=status)
    if date_from:
        sales = sales.filter(date__gte=date_from)
    if date_to:
        sales = sales.filter(date__lte=date_to)
    sales = sales.order_by('-date')[:100]
    employees = User.objects.filter(role='med_rep')
    total = sales.aggregate(t=Sum('total_amount'))['t'] or 0
    return render(request, 'sales/sales_list.html', {
        'sales': sales, 'employees': employees,
        'status_choices': Sale.STATUS_CHOICES, 'total': total
    })


@login_required
def sale_create(request):
    pharmacies = Pharmacy.objects.all()
    warehouses = Warehouse.objects.all()
    employees = User.objects.filter(role__in=['med_rep', 'sales_manager'])
    batches = Batch.objects.filter(quantity__gt=0).select_related('product', 'warehouse')
    if request.method == 'POST':
        from decimal import Decimal, InvalidOperation
        paid_raw = request.POST.get('paid_amount', '0') or '0'
        try:
            paid_amount = Decimal(paid_raw)
        except InvalidOperation:
            paid_amount = Decimal('0')

        sale = Sale(
            date=request.POST.get('date'),
            pharmacy_id=request.POST.get('pharmacy'),
            employee_id=request.POST.get('employee') or request.user.id,
            warehouse_id=request.POST.get('warehouse'),
            paid_amount=paid_amount,
            notes=request.POST.get('notes', ''),
        )
        if request.FILES.get('receipt'):
            sale.receipt = request.FILES['receipt']
        sale.save()

        total_amount = 0
        total_cost = 0
        items_data = json.loads(request.POST.get('items_json', '[]'))
        for item in items_data:
            batch = Batch.objects.get(pk=item['batch_id'])
            qty = int(item['quantity'])
            price = float(item['price'])
            cost = float(batch.purchase_price)
            SaleItem.objects.create(
                sale=sale,
                batch=batch,
                quantity=qty,
                sale_price=price,
                cost_price=cost,
            )
            total_amount += qty * price
            total_cost += qty * cost

        sale.total_amount = total_amount
        sale.total_cost = total_cost
        sale.save()
        messages.success(request, f'Продажа #{sale.pk} создана')
        return redirect('sale_detail', pk=sale.pk)
    return render(request, 'sales/sale_form.html', {
        'pharmacies': pharmacies, 'warehouses': warehouses,
        'employees': employees, 'batches': batches
    })


@login_required
def sale_detail(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    items = sale.items.select_related('batch__product', 'batch__warehouse')
    return render(request, 'sales/sale_detail.html', {'sale': sale, 'items': items})


@login_required
def sale_confirm(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    if request.method == 'POST' and sale.status == 'pending':
        sale.status = 'confirmed'
        sale.save()
        # Deduct from inventory
        for item in sale.items.all():
            batch = item.batch
            batch.quantity -= item.quantity
            batch.save()
            StockMovement.objects.create(
                movement_type='out',
                batch=batch,
                warehouse_from=batch.warehouse,
                quantity=item.quantity,
                price=item.sale_price,
                employee=request.user,
                notes=f'Продажа #{sale.pk}',
            )
        # Update pharmacy debt: only the unpaid part becomes debt
        if sale.pharmacy:
            debt_increase = sale.total_amount - sale.paid_amount
            if debt_increase > 0:
                sale.pharmacy.debt += debt_increase
                sale.pharmacy.save()
        messages.success(request, 'Продажа подтверждена, остатки обновлены')
    return redirect('sale_detail', pk=pk)


@login_required
def sales_analytics(request):
    from django.db.models.functions import TruncMonth
    from datetime import date
    monthly = Sale.objects.filter(
        status__in=['confirmed', 'shipped']
    ).annotate(month=TruncMonth('date')).values('month').annotate(
        total=Sum('total_amount'), cost=Sum('total_cost')
    ).order_by('month')[:12]

    by_employee = Sale.objects.filter(
        status__in=['confirmed', 'shipped']
    ).values('employee__first_name', 'employee__last_name').annotate(
        total=Sum('total_amount'), count=Count('id')
    ).order_by('-total')[:10]

    by_pharmacy = Sale.objects.filter(
        status__in=['confirmed', 'shipped']
    ).values('pharmacy__name').annotate(
        total=Sum('total_amount')
    ).order_by('-total')[:10]

    return render(request, 'sales/analytics.html', {
        'monthly': list(monthly),
        'by_employee': list(by_employee),
        'by_pharmacy': list(by_pharmacy),
    })


@login_required
def debts_list(request):
    pharmacies = Pharmacy.objects.filter(debt__gt=0).order_by('-debt')
    total_debt = pharmacies.aggregate(t=Sum('debt'))['t'] or 0
    recent_payments = Payment.objects.select_related('pharmacy', 'employee').order_by('-date')[:20]
    return render(request, 'sales/debts_list.html', {
        'pharmacies': pharmacies,
        'total_debt': total_debt,
        'recent_payments': recent_payments,
    })


@login_required
def payment_create(request, pharmacy_id):
    pharmacy = get_object_or_404(Pharmacy, pk=pharmacy_id)
    if request.method == 'POST':
        from decimal import Decimal, InvalidOperation
        amount_raw = request.POST.get('amount', '0') or '0'
        try:
            amount = Decimal(amount_raw)
        except InvalidOperation:
            messages.error(request, 'Неверная сумма')
            return redirect('payment_create', pharmacy_id=pharmacy_id)

        if amount <= 0:
            messages.error(request, 'Сумма должна быть больше 0')
            return redirect('payment_create', pharmacy_id=pharmacy_id)

        payment = Payment(
            pharmacy=pharmacy,
            amount=amount,
            date=request.POST.get('date') or timezone.now().date(),
            employee=request.user,
            notes=request.POST.get('notes', ''),
        )
        if request.FILES.get('receipt'):
            payment.receipt = request.FILES['receipt']
        payment.save()

        # Reduce pharmacy debt
        pharmacy.debt = max(0, pharmacy.debt - amount)
        pharmacy.save()

        messages.success(request, f'Оплата {amount:,.0f} сом принята. Остаток долга: {pharmacy.debt:,.0f} сом')
        return redirect('debts_list')

    return render(request, 'sales/payment_form.html', {'pharmacy': pharmacy})
