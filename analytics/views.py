from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from datetime import date, timedelta, datetime
from crm.models import Visit, Doctor, Pharmacy
from warehouse.models import Batch, Product
from sales.models import Sale
from accounts.models import User


@login_required
def dashboard(request):
    today = date.today()
    month_start = today.replace(day=1)

    # Sales this month
    month_sales = Sale.objects.filter(
        date__gte=month_start, status__in=['confirmed', 'shipped']
    ).aggregate(
        total=Sum('total_amount'), cost=Sum('total_cost'), count=Count('id')
    )
    total_sales = month_sales['total'] or 0
    total_cost = month_sales['cost'] or 0
    gross_profit = total_sales - total_cost
    margin_pct = round((gross_profit / total_sales * 100), 1) if total_sales > 0 else 0

    # Visits this month
    visits_count = Visit.objects.filter(
        planned_date__gte=month_start, status='done'
    ).count()
    visits_planned = Visit.objects.filter(
        planned_date__gte=month_start
    ).count()

    # Warehouse alerts
    expiring_count = Batch.objects.filter(
        expiry_date__lte=today + timedelta(days=90),
        expiry_date__gte=today,
        quantity__gt=0
    ).count()
    expired_count = Batch.objects.filter(
        expiry_date__lt=today, quantity__gt=0
    ).count()

    # Total stock value
    from django.db.models import F, ExpressionWrapper, DecimalField
    stock_value = Batch.objects.filter(
        quantity__gt=0, expiry_date__gte=today
    ).aggregate(
        val=Sum(ExpressionWrapper(F('quantity') * F('purchase_price'), output_field=DecimalField()))
    )['val'] or 0

    # Debts
    total_debt = Pharmacy.objects.aggregate(d=Sum('debt'))['d'] or 0

    # Top employees
    top_employees = Sale.objects.filter(
        date__gte=month_start, status__in=['confirmed', 'shipped']
    ).values(
        'employee__first_name', 'employee__last_name', 'employee__id'
    ).annotate(total=Sum('total_amount')).order_by('-total')[:5]

    # Recent sales
    recent_sales = Sale.objects.select_related('pharmacy', 'employee').order_by('-date')[:5]

    # Expiring products
    expiring_batches = Batch.objects.filter(
        expiry_date__lte=today + timedelta(days=90),
        expiry_date__gte=today,
        quantity__gt=0
    ).select_related('product', 'warehouse').order_by('expiry_date')[:10]

    # Pending visits
    pending_visits = Visit.objects.filter(
        status='planned',
        planned_date__date__lte=today
    ).select_related('employee', 'doctor', 'pharmacy').order_by('planned_date')[:5]

    context = {
        'total_sales': total_sales,
        'total_cost': total_cost,
        'gross_profit': gross_profit,
        'margin_pct': margin_pct,
        'visits_count': visits_count,
        'visits_planned': visits_planned,
        'expiring_count': expiring_count,
        'expired_count': expired_count,
        'stock_value': stock_value,
        'total_debt': total_debt,
        'top_employees': top_employees,
        'recent_sales': recent_sales,
        'expiring_batches': expiring_batches,
        'pending_visits': pending_visits,
        'doctors_count': Doctor.objects.count(),
        'pharmacies_count': Pharmacy.objects.count(),
    }
    return render(request, 'analytics/dashboard.html', context)


@login_required
def employee_report(request):
    employees = User.objects.filter(role__in=['med_rep', 'sales_manager'])
    today = date.today()
    month_start = today.replace(day=1)
    data = []
    for emp in employees:
        sales = Sale.objects.filter(
            employee=emp, date__gte=month_start, status__in=['confirmed', 'shipped']
        ).aggregate(total=Sum('total_amount'), count=Count('id'))
        visits = Visit.objects.filter(
            employee=emp, planned_date__gte=month_start, status='done'
        ).count()
        data.append({
            'employee': emp,
            'sales_total': sales['total'] or 0,
            'sales_count': sales['count'] or 0,
            'visits_done': visits,
        })
    data.sort(key=lambda x: x['sales_total'], reverse=True)
    return render(request, 'analytics/employee_report.html', {'data': data})
