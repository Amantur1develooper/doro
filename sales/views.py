from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count
from django.utils import timezone
from .models import Sale, SaleItem, SalesPlan, Invoice, Payment, LegalEntity
from crm.models import Pharmacy
from warehouse.models import Warehouse, Batch, StockMovement
from accounts.models import User
from crm.views import user_is_employee
import json


def _visible_employee_ids(user):
    return list(user.get_visible_users().values_list('pk', flat=True))


def _scope_sales(user):
    qs = Sale.objects.all()
    if user_is_employee(user):
        return qs.filter(employee=user)
    if user.is_manager():
        ids = _visible_employee_ids(user)
        return qs.filter(employee_id__in=ids)
    return qs


@login_required
def sales_list(request):
    sales = Sale.objects.select_related('pharmacy', 'employee', 'warehouse')
    emp_id = request.GET.get('emp')
    status = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if user_is_employee(request.user):
        sales = sales.filter(employee=request.user)
    elif request.user.is_manager():
        visible_ids = _visible_employee_ids(request.user)
        if emp_id and int(emp_id) in visible_ids:
            sales = sales.filter(employee_id=emp_id)
        else:
            sales = sales.filter(employee_id__in=visible_ids)
    else:
        if emp_id:
            sales = sales.filter(employee_id=emp_id)

    if status:
        sales = sales.filter(status=status)
    if date_from:
        sales = sales.filter(date__gte=date_from)
    if date_to:
        sales = sales.filter(date__lte=date_to)
    sales = sales.order_by('-date')[:100]

    if user_is_employee(request.user):
        employees = User.objects.filter(pk=request.user.pk)
    elif request.user.is_manager():
        employees = User.objects.filter(role='med_rep', manager=request.user)
    else:
        employees = User.objects.filter(role='med_rep')

    total = sales.aggregate(t=Sum('total_amount'))['t'] or 0
    return render(request, 'sales/sales_list.html', {
        'sales': sales, 'employees': employees,
        'status_choices': Sale.STATUS_CHOICES, 'total': total
    })


@login_required
def sale_create(request):
    if user_is_employee(request.user):
        pharmacies = Pharmacy.objects.filter(representative=request.user)
    elif request.user.is_manager():
        visible_ids = _visible_employee_ids(request.user)
        pharmacies = Pharmacy.objects.filter(representative_id__in=visible_ids)
    else:
        pharmacies = Pharmacy.objects.all()

    warehouses    = Warehouse.objects.all()
    legal_entities = LegalEntity.objects.all()
    default_entity = LegalEntity.objects.filter(is_default=True).first()

    if user_is_employee(request.user):
        employees = User.objects.filter(pk=request.user.pk)
    elif request.user.is_manager():
        employees = User.objects.filter(role='med_rep', manager=request.user)
    else:
        employees = User.objects.filter(role__in=['med_rep', 'sales_manager'])

    batches = Batch.objects.filter(quantity__gt=0).select_related('product', 'warehouse')
    batches_json = json.dumps([
        {
            'id':             b.pk,
            'name':           b.product.name,
            'sku':            b.product.sku or '',
            'batch_num':      b.batch_number or '',
            'warehouse':      b.warehouse_id,
            'warehouse_name': b.warehouse.name if b.warehouse else '',
            'qty':            b.quantity,
            'price':          float(b.product.sale_price or 0),
            'cost':           float(b.purchase_price or 0),
            'expiry':         str(b.expiry_date) if b.expiry_date else '',
        }
        for b in batches
    ])
    if request.method == 'POST':
        from decimal import Decimal, InvalidOperation
        paid_raw = request.POST.get('paid_amount', '0') or '0'
        try:
            paid_amount = Decimal(paid_raw)
        except InvalidOperation:
            paid_amount = Decimal('0')

        # Автономер накладной
        last = Sale.objects.order_by('-pk').first()
        auto_num = (last.pk + 1) if last else 1
        invoice_number = request.POST.get('invoice_number', '').strip() or str(auto_num)

        sale = Sale(
            date=request.POST.get('date'),
            pharmacy_id=request.POST.get('pharmacy'),
            employee_id=request.POST.get('employee') or request.user.id,
            warehouse_id=request.POST.get('warehouse'),
            paid_amount=paid_amount,
            notes=request.POST.get('notes', ''),
            invoice_number=invoice_number,
        )
        le_id = request.POST.get('legal_entity')
        if le_id:
            sale.legal_entity_id = le_id
        elif default_entity:
            sale.legal_entity = default_entity

        items_data = json.loads(request.POST.get('items_json') or '[]')
        if not items_data:
            messages.error(request, 'Добавьте хотя бы один товар в продажу.')
            return render(request, 'sales/sale_form.html', {
                'pharmacies': pharmacies, 'warehouses': warehouses,
                'employees': employees,
                'legal_entities': legal_entities, 'default_entity': default_entity,
                'batches_json': batches_json,
            })

        if request.FILES.get('receipt'):
            sale.receipt = request.FILES['receipt']
        sale.save()

        total_amount = 0
        total_cost = 0
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
        'employees': employees,
        'legal_entities': legal_entities, 'default_entity': default_entity,
        'batches_json': batches_json,
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
    from decimal import Decimal
    import json

    base_qs = _scope_sales(request.user).filter(status__in=['confirmed', 'shipped'])

    # ── Monthly (last 12) ──────────────────────────────────────
    monthly_raw = list(
        base_qs.annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(total=Sum('total_amount'), cost=Sum('total_cost'), cnt=Count('id'))
        .order_by('month')
    )[-12:]

    chart_months   = json.dumps([x['month'].strftime('%b %Y') for x in monthly_raw])
    chart_sales    = json.dumps([float(x['total'] or 0) for x in monthly_raw])
    chart_cost     = json.dumps([float(x['cost'] or 0) for x in monthly_raw])
    chart_profit   = json.dumps([float((x['total'] or 0) - (x['cost'] or 0)) for x in monthly_raw])
    chart_cnt      = json.dumps([x['cnt'] for x in monthly_raw])

    # ── By employee (top 8) ────────────────────────────────────
    by_employee_raw = list(
        base_qs.values('employee__first_name', 'employee__last_name')
        .annotate(total=Sum('total_amount'), cnt=Count('id'))
        .order_by('-total')[:8]
    )
    chart_emp_labels = json.dumps([
        f"{e['employee__first_name']} {e['employee__last_name']}".strip() or 'Без имени'
        for e in by_employee_raw
    ])
    chart_emp_data = json.dumps([float(e['total'] or 0) for e in by_employee_raw])

    # ── By pharmacy (top 10) ───────────────────────────────────
    by_pharmacy_raw = list(
        base_qs.values('pharmacy__name')
        .annotate(total=Sum('total_amount'), cnt=Count('id'))
        .order_by('-total')[:10]
    )
    chart_ph_labels = json.dumps([p['pharmacy__name'] or '—' for p in by_pharmacy_raw])
    chart_ph_data   = json.dumps([float(p['total'] or 0) for p in by_pharmacy_raw])

    # ── Status breakdown ───────────────────────────────────────
    all_qs = _scope_sales(request.user)
    status_raw = list(all_qs.values('status').annotate(cnt=Count('id')))
    status_map = {s['status']: s['cnt'] for s in status_raw}
    chart_status = json.dumps([
        status_map.get('confirmed', 0),
        status_map.get('pending', 0),
        status_map.get('shipped', 0),
        status_map.get('cancelled', 0),
    ])

    # ── Summary totals ─────────────────────────────────────────
    totals = base_qs.aggregate(
        total=Sum('total_amount'), cost=Sum('total_cost'), cnt=Count('id')
    )
    total_sales  = totals['total'] or Decimal(0)
    total_cost   = totals['cost'] or Decimal(0)
    gross_profit = total_sales - total_cost
    margin_pct   = round(float(gross_profit) / float(total_sales) * 100, 1) if total_sales else 0
    avg_sale     = (total_sales / totals['cnt']) if totals['cnt'] else Decimal(0)

    return render(request, 'sales/analytics.html', {
        'monthly': monthly_raw,
        'by_employee': by_employee_raw,
        'by_pharmacy': by_pharmacy_raw,
        'chart_months': chart_months,
        'chart_sales': chart_sales,
        'chart_cost': chart_cost,
        'chart_profit': chart_profit,
        'chart_cnt': chart_cnt,
        'chart_emp_labels': chart_emp_labels,
        'chart_emp_data': chart_emp_data,
        'chart_ph_labels': chart_ph_labels,
        'chart_ph_data': chart_ph_data,
        'chart_status': chart_status,
        'total_sales': total_sales,
        'gross_profit': gross_profit,
        'margin_pct': margin_pct,
        'avg_sale': avg_sale,
        'sales_count': totals['cnt'] or 0,
    })


@login_required
def debts_list(request):
    pharmacies = Pharmacy.objects.filter(debt__gt=0)

    if user_is_employee(request.user):
        pharmacies = pharmacies.filter(representative=request.user)
    elif request.user.is_manager():
        visible_ids = _visible_employee_ids(request.user)
        pharmacies = pharmacies.filter(representative_id__in=visible_ids)

    pharmacies = pharmacies.order_by('-debt')
    total_debt = pharmacies.aggregate(t=Sum('debt'))['t'] or 0

    recent_payments = Payment.objects.select_related('pharmacy', 'employee').order_by('-date')
    if user_is_employee(request.user):
        recent_payments = recent_payments.filter(pharmacy__representative=request.user)
    elif request.user.is_manager():
        visible_ids = _visible_employee_ids(request.user)
        recent_payments = recent_payments.filter(pharmacy__representative_id__in=visible_ids)
    recent_payments = recent_payments[:20]

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


@login_required
def invoice_view(request, pk):
    """HTML-накладная для печати / сохранения в PDF."""
    sale = get_object_or_404(Sale, pk=pk)
    items = sale.items.select_related('batch__product').order_by('pk')

    # Сумма прописью (простая реализация)
    def amount_words(n):
        n = int(n)
        ones = ['','один','два','три','четыре','пять','шесть','семь','восемь','девять',
                'десять','одиннадцать','двенадцать','тринадцать','четырнадцать','пятнадцать',
                'шестнадцать','семнадцать','восемнадцать','девятнадцать']
        tens = ['','','двадцать','тридцать','сорок','пятьдесят','шестьдесят','семьдесят','восемьдесят','девяносто']
        hundreds = ['','сто','двести','триста','четыреста','пятьсот','шестьсот','семьсот','восемьсот','девятьсот']
        if n == 0: return 'ноль'
        parts = []
        if n >= 1000000:
            m = n // 1000000
            parts.append(amount_words(m) + ' миллион' + ('' if m==1 else 'ов'))
            n %= 1000000
        if n >= 1000:
            t = n // 1000
            parts.append(amount_words(t) + ' тысяч')
            n %= 1000
        if n >= 100:
            parts.append(hundreds[n // 100])
            n %= 100
        if n >= 20:
            parts.append(tens[n // 10])
            n %= 10
        if n > 0:
            parts.append(ones[n])
        return ' '.join(p for p in parts if p).capitalize()

    total_words = amount_words(sale.total_amount) + ' сом'

    return render(request, 'sales/invoice_print.html', {
        'sale': sale,
        'items': items,
        'total_words': total_words,
    })
