from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Avg
from django.db.models.functions import TruncMonth
from datetime import date, timedelta
from .models import User, UserLocation
from crm.models import Region
import json
from django.http import JsonResponse
from django.utils import timezone


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Неверный логин или пароль')
    return render(request, 'accounts/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def profile_view(request):
    return render(request, 'accounts/profile.html', {'user': request.user})


@login_required
def users_list(request):
    if request.user.role not in ['superadmin', 'director']:
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')
    users = User.objects.all().select_related('region')
    return render(request, 'accounts/users_list.html', {'users': users})


@login_required
def employee_card(request, pk):
    """Дело сотрудника — полная карточка с историей и аналитикой."""
    from crm.views import user_is_employee
    from crm.models import Visit, Doctor, Pharmacy, VisitPlan
    from sales.models import Sale, SalesPlan, Payment

    employee = get_object_or_404(User, pk=pk)

    # Проверка доступа: сотрудник видит только себя
    if user_is_employee(request.user) and request.user.pk != pk:
        messages.error(request, 'Нет доступа')
        return redirect('dashboard')
    # Менеджер видит только своих подчинённых
    if request.user.is_manager():
        visible_ids = list(request.user.get_visible_users().values_list('pk', flat=True))
        if pk not in visible_ids:
            messages.error(request, 'Нет доступа')
            return redirect('dashboard')

    today = date.today()

    # ── Фильтр по периоду ─────────────────────────────────────
    period = request.GET.get('period', 'month')
    date_from_raw = request.GET.get('date_from')
    date_to_raw   = request.GET.get('date_to')

    if date_from_raw and date_to_raw:
        try:
            from datetime import datetime
            d_from = datetime.strptime(date_from_raw, '%Y-%m-%d').date()
            d_to   = datetime.strptime(date_to_raw,   '%Y-%m-%d').date()
        except ValueError:
            d_from = today.replace(day=1)
            d_to   = today
    elif period == 'week':
        d_from = today - timedelta(days=7)
        d_to   = today
    elif period == 'quarter':
        d_from = today - timedelta(days=90)
        d_to   = today
    elif period == 'year':
        d_from = today.replace(month=1, day=1)
        d_to   = today
    else:  # month
        d_from = today.replace(day=1)
        d_to   = today

    # ── Продажи ───────────────────────────────────────────────
    sales_qs = Sale.objects.filter(
        employee=employee,
        date__gte=d_from, date__lte=d_to,
        status__in=['confirmed', 'shipped']
    )
    sales_agg = sales_qs.aggregate(
        total=Sum('total_amount'), cost=Sum('total_cost'), cnt=Count('id')
    )
    sales_total  = sales_agg['total'] or 0
    sales_cost   = sales_agg['cost'] or 0
    sales_profit = sales_total - sales_cost
    sales_count  = sales_agg['cnt'] or 0
    sales_avg    = (sales_total / sales_count) if sales_count else 0

    # ── Визиты ────────────────────────────────────────────────
    visits_qs = Visit.objects.filter(
        employee=employee,
        planned_date__date__gte=d_from,
        planned_date__date__lte=d_to,
    )
    visits_done      = visits_qs.filter(status='done').count()
    visits_planned   = visits_qs.filter(status='planned').count()
    visits_cancelled = visits_qs.filter(status='cancelled').count()
    visits_total     = visits_qs.count()

    # ── План ──────────────────────────────────────────────────
    sp = SalesPlan.objects.filter(
        employee=employee, month=today.month, year=today.year
    ).first()
    vp = VisitPlan.objects.filter(
        employee=employee, month=today.month, year=today.year
    ).first()
    sales_plan_val  = float(sp.plan_amount) if sp else 0
    visits_plan_val = vp.planned_visits if vp else 0
    sales_pct       = round(float(sales_total) / sales_plan_val * 100) if sales_plan_val > 0 else 0
    visits_pct      = round(visits_done / visits_plan_val * 100) if visits_plan_val > 0 else 0

    # ── График продаж по месяцам (последние 6) ────────────────
    monthly_sales = list(
        Sale.objects.filter(
            employee=employee, status__in=['confirmed', 'shipped']
        ).annotate(m=TruncMonth('date'))
        .values('m').annotate(total=Sum('total_amount'), cnt=Count('id'))
        .order_by('m').values('m', 'total', 'cnt')
    )[-6:]
    chart_labels = json.dumps([x['m'].strftime('%b %Y') for x in monthly_sales])
    chart_sales  = json.dumps([float(x['total'] or 0) for x in monthly_sales])
    chart_cnt    = json.dumps([x['cnt'] for x in monthly_sales])

    # ── Последние продажи ─────────────────────────────────────
    recent_sales = Sale.objects.filter(
        employee=employee, date__gte=d_from, date__lte=d_to
    ).select_related('pharmacy').order_by('-date')[:20]

    # ── Последние визиты ──────────────────────────────────────
    recent_visits = Visit.objects.filter(
        employee=employee,
        planned_date__date__gte=d_from,
        planned_date__date__lte=d_to,
    ).select_related('doctor', 'pharmacy').order_by('-planned_date')[:20]

    # ── Врачи и аптеки ────────────────────────────────────────
    doctors    = Doctor.objects.filter(representative=employee).count()
    pharmacies = Pharmacy.objects.filter(representative=employee).count()

    # ── Расчёт зарплаты ───────────────────────────────────────
    salary_pct     = float(employee.salary_percent)
    salary_amount  = float(sales_total) * salary_pct / 100

    # ЗП по месяцам (последние 6) для графика
    salary_by_month = []
    for row in monthly_sales:
        salary_by_month.append(round(float(row['total'] or 0) * salary_pct / 100, 2))
    chart_salary = json.dumps(salary_by_month)

    # ── Топ аптек сотрудника ──────────────────────────────────
    top_pharmacies = list(
        sales_qs.values('pharmacy__name')
        .annotate(total=Sum('total_amount'), cnt=Count('id'))
        .order_by('-total')[:5]
    )

    # ── Планы по месяцам (текущий год) ────────────────────────
    can_edit_plan = (
        request.user.is_boss() or
        request.user.is_manager() or
        request.user.pk == pk
    )
    year_plans = []
    MONTHS_RU = ['Январь','Февраль','Март','Апрель','Май','Июнь',
                 'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь']
    existing_vp = {
        vp.month: vp
        for vp in VisitPlan.objects.filter(employee=employee, year=today.year)
    }
    existing_sp = {
        sp.month: sp
        for sp in SalesPlan.objects.filter(employee=employee, year=today.year)
    }
    for m in range(1, 13):
        year_plans.append({
            'month': m,
            'month_name': MONTHS_RU[m-1],
            'is_current': m == today.month,
            'vp': existing_vp.get(m),
            'sp': existing_sp.get(m),
        })

    context = {
        'can_edit_plan': can_edit_plan,
        'year_plans': year_plans,
        'current_year': today.year,
        'salary_pct': salary_pct,
        'salary_amount': salary_amount,
        'chart_salary': chart_salary,
        'employee': employee,
        'period': period,
        'd_from': d_from,
        'd_to': d_to,
        'date_from_raw': date_from_raw or '',
        'date_to_raw': date_to_raw or '',
        # stats
        'sales_total': sales_total,
        'sales_profit': sales_profit,
        'sales_count': sales_count,
        'sales_avg': sales_avg,
        'visits_done': visits_done,
        'visits_planned_cnt': visits_planned,
        'visits_cancelled': visits_cancelled,
        'visits_total': visits_total,
        # plan
        'sales_plan_val': sales_plan_val,
        'visits_plan_val': visits_plan_val,
        'sales_pct': min(sales_pct, 100),
        'visits_pct': min(visits_pct, 100),
        # chart
        'chart_labels': chart_labels,
        'chart_sales': chart_sales,
        'chart_cnt': chart_cnt,
        # lists
        'recent_sales': recent_sales,
        'recent_visits': recent_visits,
        'top_pharmacies': top_pharmacies,
        'doctors_count': doctors,
        'pharmacies_count': pharmacies,
    }
    return render(request, 'accounts/employee_card.html', context)


@login_required
def set_employee_plan(request, pk):
    """Сохранить план визитов и продаж для сотрудника на месяц/год."""
    from crm.models import VisitPlan
    from sales.models import SalesPlan
    from decimal import Decimal, InvalidOperation

    employee = get_object_or_404(User, pk=pk)

    # Доступ: только boss или manager своего подчинённого
    if not (request.user.is_boss() or request.user.is_manager()):
        messages.error(request, 'Нет прав для изменения плана')
        return redirect('employee_card', pk=pk)

    if request.method == 'POST':
        month = int(request.POST.get('month', date.today().month))
        year  = int(request.POST.get('year', date.today().year))

        # План визитов
        visits_raw = request.POST.get('planned_visits', '').strip()
        if visits_raw:
            try:
                vp_val = int(visits_raw)
                vp, _ = VisitPlan.objects.get_or_create(
                    employee=employee, month=month, year=year,
                    defaults={'planned_visits': 0}
                )
                vp.planned_visits = vp_val
                vp.save()
            except ValueError:
                pass

        # План продаж
        sales_raw = request.POST.get('plan_amount', '').strip()
        if sales_raw:
            try:
                sp_val = Decimal(sales_raw)
                sp, _ = SalesPlan.objects.get_or_create(
                    employee=employee, month=month, year=year,
                    defaults={'plan_amount': 0}
                )
                sp.plan_amount = sp_val
                sp.save()
            except InvalidOperation:
                pass

        messages.success(request, f'План на {month}/{year} сохранён')

    return redirect('employee_card', pk=pk)


@login_required
def set_salary_percent(request, pk):
    """Изменить процент ЗП сотрудника."""
    from decimal import Decimal, InvalidOperation
    employee = get_object_or_404(User, pk=pk)
    if not request.user.is_boss():
        messages.error(request, 'Только директор может изменять % ЗП')
        return redirect('employee_card', pk=pk)
    if request.method == 'POST':
        pct_raw = request.POST.get('salary_percent', '').strip()
        try:
            pct = Decimal(pct_raw)
            if 0 <= pct <= 100:
                employee.salary_percent = pct
                employee.save(update_fields=['salary_percent'])
                messages.success(request, f'Процент ЗП изменён на {pct}%')
            else:
                messages.error(request, 'Процент должен быть от 0 до 100')
        except InvalidOperation:
            messages.error(request, 'Неверное значение')
    return redirect('employee_card', pk=pk)


@login_required
def user_create(request):
    if request.user.role not in ['superadmin']:
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')
    regions = Region.objects.all()
    if request.method == 'POST':
        u = User(
            username=request.POST.get('username'),
            first_name=request.POST.get('first_name'),
            last_name=request.POST.get('last_name'),
            email=request.POST.get('email'),
            phone=request.POST.get('phone'),
            role=request.POST.get('role'),
        )
        region_id = request.POST.get('region')
        if region_id:
            u.region_id = region_id
        u.set_password(request.POST.get('password'))
        u.save()
        messages.success(request, 'Пользователь создан')
        return redirect('users_list')
    return render(request, 'accounts/user_form.html', {'regions': regions, 'action': 'create'})


@login_required
def update_location(request):
    """Принимает GPS координаты от сотрудника и сохраняет."""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    try:
        data = json.loads(request.body)
        lat  = float(data['lat'])
        lng  = float(data['lng'])
    except (KeyError, ValueError, json.JSONDecodeError):
        return JsonResponse({'ok': False, 'error': 'bad data'}, status=400)

    UserLocation.objects.update_or_create(
        user=request.user,
        defaults={
            'latitude':  lat,
            'longitude': lng,
            'address':   data.get('address', ''),
            'is_active': True,
        }
    )
    return JsonResponse({'ok': True})


@login_required
def location_map(request):
    """Карта местоположения сотрудников (только для менеджеров и боссов)."""
    if not (request.user.is_boss() or request.user.is_manager()):
        messages.error(request, 'Доступ запрещён')
        return redirect('dashboard')

    visible = request.user.get_visible_users().filter(
        role__in=['med_rep', 'sales_manager', 'warehouse']
    ).exclude(pk=request.user.pk)

    # Подгружаем локации
    from django.utils import timezone as tz
    from datetime import timedelta
    cutoff = tz.now() - timedelta(hours=24)

    locations = []
    for u in visible.select_related('location'):
        loc = getattr(u, 'location', None)
        if loc:
            now      = tz.now()
            online   = loc.updated_at >= (now - timedelta(minutes=15))
            away     = not online and loc.updated_at >= (now - timedelta(hours=2))
            recent   = loc.updated_at >= cutoff
            if recent:
                locations.append({
                    'id':       u.pk,
                    'name':     u.get_full_name() or u.username,
                    'role':     u.get_role_display(),
                    'lat':      float(loc.latitude),
                    'lng':      float(loc.longitude),
                    'address':  loc.address,
                    'updated':  loc.updated_at.strftime('%d.%m %H:%M'),
                    'online':   online,
                    'away':     away,
                    'url':      f'/accounts/users/{u.pk}/',
                })

    return render(request, 'accounts/location_map.html', {
        'locations_json': json.dumps(locations, ensure_ascii=False),
        'total_employees': visible.count(),
        'active_count': sum(1 for l in locations if l['online']),
    })
