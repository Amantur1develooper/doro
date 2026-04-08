from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
from datetime import date, timedelta
from crm.models import Visit, Doctor, Pharmacy, VisitPlan
from warehouse.models import Batch
from sales.models import Sale, SalesPlan
from accounts.models import User
from crm.views import user_is_employee
import json


def _scope_sales(user):
    """QuerySet продаж видимых этому пользователю."""
    qs = Sale.objects.all()
    if user_is_employee(user):
        return qs.filter(employee=user)
    if user.is_manager():
        ids = list(user.get_visible_users().values_list('pk', flat=True))
        return qs.filter(employee_id__in=ids)
    return qs


def _scope_visits(user):
    qs = Visit.objects.all()
    if user_is_employee(user):
        return qs.filter(employee=user)
    if user.is_manager():
        ids = list(user.get_visible_users().values_list('pk', flat=True))
        return qs.filter(employee_id__in=ids)
    return qs


def _scope_doctors(user):
    qs = Doctor.objects.all()
    if user_is_employee(user):
        return qs.filter(representative=user)
    if user.is_manager():
        ids = list(user.get_visible_users().values_list('pk', flat=True))
        return qs.filter(representative_id__in=ids)
    return qs


def _scope_pharmacies(user):
    qs = Pharmacy.objects.all()
    if user_is_employee(user):
        return qs.filter(representative=user)
    if user.is_manager():
        ids = list(user.get_visible_users().values_list('pk', flat=True))
        return qs.filter(representative_id__in=ids)
    return qs


@login_required
def dashboard(request):
    today = date.today()
    month_start = today.replace(day=1)

    sales_qs = _scope_sales(request.user)
    visits_qs = _scope_visits(request.user)

    # ── Stat cards ─────────────────────────────────────────────
    month_sales = sales_qs.filter(
        date__gte=month_start, status__in=['confirmed', 'shipped']
    ).aggregate(total=Sum('total_amount'), cost=Sum('total_cost'), count=Count('id'))
    total_sales  = month_sales['total'] or 0
    total_cost   = month_sales['cost'] or 0
    gross_profit = total_sales - total_cost
    margin_pct   = round((gross_profit / total_sales * 100), 1) if total_sales > 0 else 0

    visits_done    = visits_qs.filter(planned_date__gte=month_start, status='done').count()
    visits_planned = visits_qs.filter(planned_date__gte=month_start).count()

    expiring_count = Batch.objects.filter(
        expiry_date__lte=today + timedelta(days=90),
        expiry_date__gte=today, quantity__gt=0
    ).count()
    expired_count = Batch.objects.filter(expiry_date__lt=today, quantity__gt=0).count()

    from django.db.models import F, ExpressionWrapper, DecimalField
    stock_value = Batch.objects.filter(quantity__gt=0, expiry_date__gte=today).aggregate(
        val=Sum(ExpressionWrapper(F('quantity') * F('purchase_price'), output_field=DecimalField()))
    )['val'] or 0

    total_debt = _scope_pharmacies(request.user).aggregate(d=Sum('debt'))['d'] or 0

    # ── Chart 1: продажи по месяцам (last 6) ───────────────────
    monthly_sales = list(
        sales_qs.filter(status__in=['confirmed', 'shipped'])
        .annotate(m=TruncMonth('date'))
        .values('m')
        .annotate(total=Sum('total_amount'), profit=Sum('total_amount') - Sum('total_cost'))
        .order_by('m')
        .values('m', 'total', 'profit')
    )[-6:]
    chart_sales_labels = [x['m'].strftime('%b %Y') if x['m'] else '' for x in monthly_sales]
    chart_sales_data   = [float(x['total'] or 0) for x in monthly_sales]
    chart_profit_data  = [float(x['profit'] or 0) for x in monthly_sales]

    # ── Chart 2: визиты по статусам ────────────────────────────
    visit_stats = visits_qs.values('status').annotate(cnt=Count('id'))
    vstatus = {v['status']: v['cnt'] for v in visit_stats}
    chart_visits = [
        vstatus.get('done', 0),
        vstatus.get('planned', 0),
        vstatus.get('cancelled', 0),
        vstatus.get('postponed', 0),
    ]

    # ── Chart 3: визиты по месяцам ─────────────────────────────
    monthly_visits = list(
        visits_qs.filter(status='done')
        .annotate(m=TruncMonth('planned_date'))
        .values('m')
        .annotate(cnt=Count('id'))
        .order_by('m')
        .values('m', 'cnt')
    )[-6:]
    chart_visits_labels = [x['m'].strftime('%b %Y') if x['m'] else '' for x in monthly_visits]
    chart_visits_cnt    = [x['cnt'] for x in monthly_visits]

    # ── Top employees (boss/manager) ───────────────────────────
    top_employees = []
    if not user_is_employee(request.user):
        top_employees = list(
            sales_qs.filter(date__gte=month_start, status__in=['confirmed', 'shipped'])
            .values('employee__first_name', 'employee__last_name', 'employee__id')
            .annotate(total=Sum('total_amount'), cnt=Count('id'))
            .order_by('-total')[:5]
        )

    # ── My plan vs fact (employee / manager) ───────────────────
    my_plan = None
    my_sales_fact = None
    my_visits_plan = None
    my_visits_fact = None
    if user_is_employee(request.user) or request.user.is_manager():
        sp = SalesPlan.objects.filter(
            employee=request.user, month=today.month, year=today.year
        ).first()
        my_plan = float(sp.plan_amount) if sp else None
        my_sales_fact = float(sales_qs.filter(
            date__gte=month_start, status__in=['confirmed', 'shipped']
        ).aggregate(t=Sum('total_amount'))['t'] or 0)

        vp = VisitPlan.objects.filter(
            employee=request.user, month=today.month, year=today.year
        ).first()
        my_visits_plan = vp.planned_visits if vp else None
        my_visits_fact = visits_done

    # ── Subordinates summary (manager) ─────────────────────────
    subordinates_data = []
    if request.user.is_manager():
        for sub in request.user.get_visible_users().exclude(pk=request.user.pk):
            s = sales_qs.filter(
                employee=sub, date__gte=month_start, status__in=['confirmed', 'shipped']
            ).aggregate(total=Sum('total_amount'), cnt=Count('id'))
            v_done = visits_qs.filter(
                employee=sub, planned_date__gte=month_start, status='done'
            ).count()
            subordinates_data.append({
                'employee': sub,
                'sales_total': s['total'] or 0,
                'sales_count': s['cnt'] or 0,
                'visits_done': v_done,
            })
        subordinates_data.sort(key=lambda x: x['sales_total'], reverse=True)

    # ── Widget lists ───────────────────────────────────────────
    recent_sales = sales_qs.select_related('pharmacy', 'employee').order_by('-date')[:5]
    expiring_batches = Batch.objects.filter(
        expiry_date__lte=today + timedelta(days=90),
        expiry_date__gte=today, quantity__gt=0
    ).select_related('product', 'warehouse').order_by('expiry_date')[:8]
    pending_visits = visits_qs.filter(
        status='planned', planned_date__date__lte=today
    ).select_related('employee', 'doctor', 'pharmacy').order_by('planned_date')[:5]

    context = {
        'total_sales': total_sales,
        'gross_profit': gross_profit,
        'margin_pct': margin_pct,
        'visits_done': visits_done,
        'visits_planned': visits_planned,
        'expiring_count': expiring_count,
        'expired_count': expired_count,
        'stock_value': stock_value,
        'total_debt': total_debt,
        'doctors_count': _scope_doctors(request.user).count(),
        'pharmacies_count': _scope_pharmacies(request.user).count(),
        # charts
        'chart_sales_labels': json.dumps(chart_sales_labels),
        'chart_sales_data': json.dumps(chart_sales_data),
        'chart_profit_data': json.dumps(chart_profit_data),
        'chart_visits': json.dumps(chart_visits),
        'chart_visits_labels': json.dumps(chart_visits_labels),
        'chart_visits_cnt': json.dumps(chart_visits_cnt),
        # lists
        'top_employees': top_employees,
        'recent_sales': recent_sales,
        'expiring_batches': expiring_batches,
        'pending_visits': pending_visits,
        # plan
        'my_plan': my_plan,
        'my_sales_fact': my_sales_fact,
        'my_visits_plan': my_visits_plan,
        'my_visits_fact': my_visits_fact,
        # manager
        'subordinates_data': subordinates_data,
    }
    return render(request, 'analytics/dashboard.html', context)


@login_required
def my_analytics(request):
    """Личная аналитика текущего пользователя."""
    today = date.today()
    month_start = today.replace(day=1)
    year_start  = today.replace(month=1, day=1)

    sales_qs  = Sale.objects.filter(employee=request.user)
    visits_qs = Visit.objects.filter(employee=request.user)

    # ── 6-month sales chart ────────────────────────────────────
    monthly_sales = list(
        sales_qs.filter(status__in=['confirmed', 'shipped'])
        .annotate(m=TruncMonth('date'))
        .values('m').annotate(total=Sum('total_amount'))
        .order_by('m').values('m', 'total')
    )[-6:]
    chart_sales_labels = [x['m'].strftime('%b %Y') if x['m'] else '' for x in monthly_sales]
    chart_sales_data   = [float(x['total'] or 0) for x in monthly_sales]

    # ── 6-month visits chart ───────────────────────────────────
    monthly_visits = list(
        visits_qs.filter(status='done')
        .annotate(m=TruncMonth('planned_date'))
        .values('m').annotate(cnt=Count('id'))
        .order_by('m').values('m', 'cnt')
    )[-6:]
    chart_visits_labels = [x['m'].strftime('%b %Y') if x['m'] else '' for x in monthly_visits]
    chart_visits_cnt    = [x['cnt'] for x in monthly_visits]

    # ── Visit status donut ─────────────────────────────────────
    vstats = visits_qs.filter(planned_date__year=today.year).values('status').annotate(cnt=Count('id'))
    vstatus = {v['status']: v['cnt'] for v in vstats}

    # ── This month stats ───────────────────────────────────────
    month_s = sales_qs.filter(
        date__gte=month_start, status__in=['confirmed', 'shipped']
    ).aggregate(total=Sum('total_amount'), cnt=Count('id'))
    month_v_done    = visits_qs.filter(planned_date__gte=month_start, status='done').count()
    month_v_planned = visits_qs.filter(planned_date__gte=month_start).count()

    # ── Plan ───────────────────────────────────────────────────
    sales_plan = SalesPlan.objects.filter(
        employee=request.user, month=today.month, year=today.year
    ).first()
    visit_plan = VisitPlan.objects.filter(
        employee=request.user, month=today.month, year=today.year
    ).first()

    sales_fact = float(month_s['total'] or 0)
    sales_plan_val = float(sales_plan.plan_amount) if sales_plan else 0
    sales_pct = round(sales_fact / sales_plan_val * 100) if sales_plan_val > 0 else 0

    visits_plan_val = visit_plan.planned_visits if visit_plan else 0
    visits_pct = round(month_v_done / visits_plan_val * 100) if visits_plan_val > 0 else 0

    # ── Recent visits ──────────────────────────────────────────
    recent_visits = visits_qs.select_related('doctor', 'pharmacy').order_by('-planned_date')[:10]
    recent_sales  = sales_qs.select_related('pharmacy').order_by('-date')[:10]

    context = {
        'chart_sales_labels': json.dumps(chart_sales_labels),
        'chart_sales_data': json.dumps(chart_sales_data),
        'chart_visits_labels': json.dumps(chart_visits_labels),
        'chart_visits_cnt': json.dumps(chart_visits_cnt),
        'chart_vstatus': json.dumps([
            vstatus.get('done', 0), vstatus.get('planned', 0),
            vstatus.get('cancelled', 0), vstatus.get('postponed', 0),
        ]),
        'month_sales_total': month_s['total'] or 0,
        'month_sales_count': month_s['cnt'] or 0,
        'month_v_done': month_v_done,
        'month_v_planned': month_v_planned,
        'sales_fact': sales_fact,
        'sales_plan_val': sales_plan_val,
        'sales_pct': min(sales_pct, 100),
        'visits_plan_val': visits_plan_val,
        'visits_pct': min(visits_pct, 100),
        'doctors_count': Doctor.objects.filter(representative=request.user).count(),
        'pharmacies_count': Pharmacy.objects.filter(representative=request.user).count(),
        'recent_visits': recent_visits,
        'recent_sales': recent_sales,
    }
    return render(request, 'analytics/my_analytics.html', context)


@login_required
def employee_report(request):
    """Отчёт по сотрудникам (только для boss/manager)."""
    today = date.today()
    month_start = today.replace(day=1)

    if user_is_employee(request.user):
        from django.shortcuts import redirect
        return redirect('my_analytics')

    if request.user.is_manager():
        employees = request.user.get_visible_users().exclude(pk=request.user.pk)
    else:
        employees = User.objects.filter(role__in=['med_rep', 'sales_manager'])

    data = []
    for emp in employees:
        s = Sale.objects.filter(
            employee=emp, date__gte=month_start, status__in=['confirmed', 'shipped']
        ).aggregate(total=Sum('total_amount'), count=Count('id'))
        v_done    = Visit.objects.filter(employee=emp, planned_date__gte=month_start, status='done').count()
        v_planned = Visit.objects.filter(employee=emp, planned_date__gte=month_start).count()
        sp = SalesPlan.objects.filter(employee=emp, month=today.month, year=today.year).first()
        vp = VisitPlan.objects.filter(employee=emp, month=today.month, year=today.year).first()
        plan_val = float(sp.plan_amount) if sp else 0
        fact_val = float(s['total'] or 0)
        data.append({
            'employee': emp,
            'sales_total': fact_val,
            'sales_count': s['count'] or 0,
            'visits_done': v_done,
            'visits_planned': v_planned,
            'sales_plan': plan_val,
            'sales_pct': round(fact_val / plan_val * 100) if plan_val > 0 else 0,
            'visits_plan': vp.planned_visits if vp else 0,
            'visits_pct': round(v_done / vp.planned_visits * 100) if vp and vp.planned_visits > 0 else 0,
        })
    data.sort(key=lambda x: x['sales_total'], reverse=True)

    # Bar chart: top 8 employees by sales
    chart_labels = json.dumps([f"{d['employee'].get_full_name() or d['employee'].username}" for d in data[:8]])
    chart_facts  = json.dumps([d['sales_total'] for d in data[:8]])
    chart_plans  = json.dumps([d['sales_plan'] for d in data[:8]])

    return render(request, 'analytics/employee_report.html', {
        'data': data,
        'chart_labels': chart_labels,
        'chart_facts': chart_facts,
        'chart_plans': chart_plans,
    })
