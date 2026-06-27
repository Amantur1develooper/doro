import calendar
import json
from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
from .models import Doctor, Pharmacy, Visit, VisitPhoto, VisitAudio, VisitPlan, Region
from accounts.models import User


def _visible_user_ids(user):
    """Возвращает список pk пользователей, которых может видеть user."""
    return list(user.get_visible_users().values_list('pk', flat=True))


@login_required
def doctors_list(request):
    doctors = Doctor.objects.select_related('region', 'representative')
    region_id = request.GET.get('region')
    rep_id = request.GET.get('rep')
    search = request.GET.get('q', '')

    # Иерархия: сотрудник видит только своих врачей
    if user_is_employee(request.user):
        doctors = doctors.filter(representative=request.user)
    elif request.user.is_manager():
        visible_ids = _visible_user_ids(request.user)
        doctors = doctors.filter(representative_id__in=visible_ids)
    # boss видит всех

    if region_id:
        doctors = doctors.filter(region_id=region_id)
    if rep_id and not user_is_employee(request.user):
        doctors = doctors.filter(representative_id=rep_id)
    if search:
        doctors = doctors.filter(full_name__icontains=search)

    regions = Region.objects.all()
    reps = _get_visible_reps(request.user)

    # Статистика по сотрудникам для менеджера/босса
    rep_stats = []
    if request.user.is_manager() or request.user.is_boss():
        qs_base = Doctor.objects.all()
        if request.user.is_manager():
            visible_ids = _visible_user_ids(request.user)
            qs_base = qs_base.filter(representative_id__in=visible_ids)
        rep_stats = list(
            qs_base.values('representative__pk', 'representative__first_name',
                           'representative__last_name', 'representative__username')
            .annotate(cnt=Count('id'))
            .order_by('-cnt')
        )

    return render(request, 'crm/doctors_list.html', {
        'doctors': doctors, 'regions': regions, 'reps': reps, 'search': search,
        'is_employee': user_is_employee(request.user),
        'rep_stats': rep_stats,
        'selected_rep': rep_id,
    })


@login_required
def doctor_detail(request, pk):
    doctor = get_object_or_404(Doctor, pk=pk)
    # Доступ: boss и manager видят всех, сотрудник — только своих
    if user_is_employee(request.user) and doctor.representative != request.user:
        messages.error(request, 'Нет доступа к этому врачу')
        return redirect('doctors_list')
    visits = Visit.objects.filter(doctor=doctor).select_related('employee').order_by('-planned_date')[:20]
    return render(request, 'crm/doctor_detail.html', {'doctor': doctor, 'visits': visits})


@login_required
def doctor_create(request):
    regions = Region.objects.all()
    reps = _get_visible_reps(request.user)
    is_emp = user_is_employee(request.user)
    if request.method == 'POST':
        d = Doctor(
            full_name=request.POST.get('full_name', '').strip(),
            specialty=request.POST.get('specialty', '').strip(),
            institution=request.POST.get('institution', '').strip(),
            phone=request.POST.get('phone', '').strip(),
            address=request.POST.get('address', '').strip(),
            notes=request.POST.get('notes', ''),
        )
        region_id = request.POST.get('region')
        if region_id:
            d.region_id = region_id

        # Сотрудник ВСЕГДА привязывается к себе — нельзя создать чужого врача
        if is_emp:
            d.representative = request.user
        else:
            rep_id = request.POST.get('representative')
            if rep_id:
                d.representative_id = rep_id

        if request.FILES.get('photo'):
            d.photo = request.FILES['photo']
        d.save()
        messages.success(request, f'Врач «{d.full_name}» добавлен')
        return redirect('doctors_list')
    return render(request, 'crm/doctor_form.html', {
        'regions': regions, 'reps': reps, 'is_employee': is_emp,
    })


@login_required
def doctor_edit(request, pk):
    doctor = get_object_or_404(Doctor, pk=pk)
    # Доступ: сотрудник — только свой, менеджер/босс — любой
    if user_is_employee(request.user) and doctor.representative != request.user:
        messages.error(request, 'Нет доступа')
        return redirect('doctor_detail', pk=pk)

    regions = Region.objects.all()
    reps = _get_visible_reps(request.user)
    is_emp = user_is_employee(request.user)

    if request.method == 'POST':
        doctor.full_name   = request.POST.get('full_name', '').strip()
        doctor.specialty   = request.POST.get('specialty', '').strip()
        doctor.institution = request.POST.get('institution', '').strip()
        doctor.phone       = request.POST.get('phone', '').strip()
        doctor.address     = request.POST.get('address', '').strip()
        doctor.notes       = request.POST.get('notes', '')
        region_id = request.POST.get('region')
        doctor.region_id = region_id if region_id else None
        if not is_emp:
            rep_id = request.POST.get('representative')
            doctor.representative_id = rep_id if rep_id else None
        if request.FILES.get('photo'):
            doctor.photo = request.FILES['photo']
        elif request.POST.get('clear_photo'):
            doctor.photo = None
        doctor.save()
        messages.success(request, f'Врач «{doctor.full_name}» обновлён')
        return redirect('doctor_detail', pk=pk)

    return render(request, 'crm/doctor_edit.html', {
        'doctor': doctor, 'regions': regions, 'reps': reps, 'is_employee': is_emp,
    })


@login_required
def pharmacies_list(request):
    pharmacies = Pharmacy.objects.select_related('region', 'representative')
    region_id = request.GET.get('region')
    search = request.GET.get('q', '')

    # Иерархия: сотрудник видит только свои аптеки
    if user_is_employee(request.user):
        pharmacies = pharmacies.filter(representative=request.user)
    elif request.user.is_manager():
        visible_ids = _visible_user_ids(request.user)
        pharmacies = pharmacies.filter(representative_id__in=visible_ids)

    if region_id:
        pharmacies = pharmacies.filter(region_id=region_id)
    if search:
        pharmacies = pharmacies.filter(name__icontains=search)

    regions = Region.objects.all()
    return render(request, 'crm/pharmacies_list.html', {
        'pharmacies': pharmacies, 'regions': regions, 'search': search,
        'is_employee': user_is_employee(request.user),
    })


@login_required
def pharmacy_detail(request, pk):
    pharmacy = get_object_or_404(Pharmacy, pk=pk)
    # Доступ: сотрудник видит только свои аптеки
    if user_is_employee(request.user) and pharmacy.representative != request.user:
        messages.error(request, 'Нет доступа к этой аптеке')
        return redirect('pharmacies_list')
    visits = Visit.objects.filter(pharmacy=pharmacy).select_related('employee').order_by('-planned_date')[:20]
    from sales.models import Sale
    sales = Sale.objects.filter(pharmacy=pharmacy).order_by('-date')[:10]
    return render(request, 'crm/pharmacy_detail.html', {
        'pharmacy': pharmacy, 'visits': visits, 'sales': sales
    })


@login_required
def pharmacy_create(request):
    regions = Region.objects.all()
    reps = _get_visible_reps(request.user)
    is_emp = user_is_employee(request.user)
    if request.method == 'POST':
        p = Pharmacy(
            name=request.POST.get('name', '').strip(),
            address=request.POST.get('address', '').strip(),
            contact_person=request.POST.get('contact_person', '').strip(),
            phone=request.POST.get('phone', '').strip(),
            notes=request.POST.get('notes', ''),
        )
        region_id = request.POST.get('region')
        if region_id:
            p.region_id = region_id
        # Сотрудник ВСЕГДА привязывается к себе
        if is_emp:
            p.representative = request.user
        else:
            rep_id = request.POST.get('representative')
            if rep_id:
                p.representative_id = rep_id
        p.save()
        messages.success(request, f'Аптека «{p.name}» добавлена')
        return redirect('pharmacies_list')
    return render(request, 'crm/pharmacy_form.html', {
        'regions': regions, 'reps': reps, 'is_employee': is_emp,
    })


@login_required
def visits_list(request):
    visits = Visit.objects.select_related('employee', 'doctor', 'pharmacy')
    emp_id = request.GET.get('emp')
    status = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    # Иерархия
    if user_is_employee(request.user):
        visits = visits.filter(employee=request.user)
    elif request.user.is_manager():
        visible_ids = _visible_user_ids(request.user)
        if emp_id and int(emp_id) in visible_ids:
            visits = visits.filter(employee_id=emp_id)
        else:
            visits = visits.filter(employee_id__in=visible_ids)
    else:
        # boss
        if emp_id:
            visits = visits.filter(employee_id=emp_id)

    if status:
        visits = visits.filter(status=status)
    if date_from:
        visits = visits.filter(planned_date__date__gte=date_from)
    if date_to:
        visits = visits.filter(planned_date__date__lte=date_to)

    visits = visits.order_by('-planned_date')[:100]
    employees = _get_visible_reps(request.user)
    return render(request, 'crm/visits_list.html', {
        'visits': visits, 'employees': employees,
        'status_choices': Visit.STATUS_CHOICES,
        'is_employee': user_is_employee(request.user),
    })


@login_required
def visit_create(request):
    # Врачи и аптеки — только видимые текущему пользователю
    if user_is_employee(request.user):
        doctors = Doctor.objects.filter(representative=request.user)
        pharmacies = Pharmacy.objects.filter(representative=request.user)
    elif request.user.is_manager():
        visible_ids = _visible_user_ids(request.user)
        doctors = Doctor.objects.filter(representative_id__in=visible_ids)
        pharmacies = Pharmacy.objects.filter(representative_id__in=visible_ids)
    else:
        doctors = Doctor.objects.all()
        pharmacies = Pharmacy.objects.all()

    employees = _get_visible_reps(request.user)

    if request.method == 'POST':
        planned_raw = request.POST.get('planned_date', '')
        planned_dt = parse_datetime(planned_raw)
        if planned_dt is None:
            d = parse_date(planned_raw)
            planned_dt = timezone.make_aware(
                timezone.datetime(d.year, d.month, d.day, 9, 0)
            ) if d else timezone.now()
        elif timezone.is_naive(planned_dt):
            planned_dt = timezone.make_aware(planned_dt)

        # Сотрудник может создавать визит только для себя
        if user_is_employee(request.user):
            employee_id = request.user.id
        else:
            employee_id = request.POST.get('employee') or request.user.id

        v = Visit(
            employee_id=employee_id,
            visit_type=request.POST.get('visit_type'),
            status=request.POST.get('status', 'planned'),
            planned_date=planned_dt,
            comment=request.POST.get('comment', ''),
            result=request.POST.get('result', ''),
        )
        if v.visit_type == 'doctor':
            v.doctor_id = request.POST.get('doctor')
        else:
            v.pharmacy_id = request.POST.get('pharmacy')
        v.save()
        for photo in request.FILES.getlist('photos'):
            VisitPhoto.objects.create(visit=v, photo=photo)
        for audio in request.FILES.getlist('audios'):
            VisitAudio.objects.create(visit=v, audio=audio)
        messages.success(request, 'Визит создан')
        return redirect('visits_list')
    return render(request, 'crm/visit_form.html', {
        'doctors': doctors, 'pharmacies': pharmacies, 'employees': employees,
        'is_employee': user_is_employee(request.user),
    })


@login_required
def visit_detail(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    # Сотрудник видит только свой визит
    if user_is_employee(request.user) and visit.employee != request.user:
        messages.error(request, 'Нет доступа к этому визиту')
        return redirect('visits_list')
    can_edit = (
        request.user.is_boss() or
        request.user.is_manager() or
        visit.employee == request.user
    )
    return render(request, 'crm/visit_detail.html', {'visit': visit, 'can_edit': can_edit})


@login_required
def visit_edit(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    # Доступ: свой визит или менеджер/босс
    if user_is_employee(request.user) and visit.employee != request.user:
        messages.error(request, 'Нет доступа')
        return redirect('visits_list')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'cancel':
            visit.status = 'cancelled'
            visit.save(update_fields=['status'])
            messages.success(request, 'Визит отменён')
            return redirect('visits_list')

        # Обычное редактирование
        planned_raw = request.POST.get('planned_date', '')
        planned_dt = parse_datetime(planned_raw)
        if planned_dt is None:
            d = parse_date(planned_raw)
            if d:
                planned_dt = timezone.make_aware(
                    timezone.datetime(d.year, d.month, d.day, 9, 0)
                )
        elif timezone.is_naive(planned_dt):
            planned_dt = timezone.make_aware(planned_dt)

        if planned_dt:
            visit.planned_date = planned_dt

        new_status = request.POST.get('status')
        if new_status in dict(Visit.STATUS_CHOICES):
            visit.status = new_status

        visit.comment = request.POST.get('comment', '')
        visit.result  = request.POST.get('result', '')
        visit.save(update_fields=['planned_date', 'status', 'comment', 'result'])
        messages.success(request, 'Визит обновлён')
        return redirect('visit_detail', pk=pk)

    return render(request, 'crm/visit_edit.html', {'visit': visit})


@login_required
def visit_complete(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    if user_is_employee(request.user) and visit.employee != request.user:
        messages.error(request, 'Нет доступа')
        return redirect('visits_list')
    if request.method == 'POST':
        visit.status = 'done'
        visit.actual_date = timezone.now()
        lat = request.POST.get('latitude')
        lng = request.POST.get('longitude')
        if lat:
            visit.latitude = lat
        if lng:
            visit.longitude = lng
        visit.result = request.POST.get('result', '')
        visit.save()
        for photo in request.FILES.getlist('photos'):
            VisitPhoto.objects.create(visit=visit, photo=photo)
        messages.success(request, 'Визит отмечен как выполненный')
    return redirect('visit_detail', pk=pk)


@login_required
def calendar_view(request):
    today = date.today()
    year  = int(request.GET.get('year',  today.year))
    month = int(request.GET.get('month', today.month))

    # Навигация месяц ±1
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    # Визиты за месяц
    visits_qs = Visit.objects.select_related(
        'employee', 'doctor', 'pharmacy'
    ).filter(
        planned_date__year=year, planned_date__month=month
    )
    if user_is_employee(request.user):
        visits_qs = visits_qs.filter(employee=request.user)
    elif request.user.is_manager():
        visible_ids = _visible_user_ids(request.user)
        visits_qs = visits_qs.filter(employee_id__in=visible_ids)

    # Фильтр по сотруднику (для менеджера/босса)
    filter_emp = request.GET.get('emp')
    if filter_emp and not user_is_employee(request.user):
        visits_qs = visits_qs.filter(employee_id=filter_emp)

    # Цвета сотрудников
    COLORS = ['#3b82f6','#8b5cf6','#ec4899','#f97316','#14b8a6','#84cc16','#f43f5e','#0ea5e9']
    emp_colors = {}
    color_idx = 0

    # Сериализуем визиты в JSON (безопасно — без обращений к None в шаблоне)
    visits_json_list = []
    for v in visits_qs.order_by('planned_date'):
        if v.employee_id not in emp_colors:
            emp_colors[v.employee_id] = COLORS[color_idx % len(COLORS)]
            color_idx += 1
        target = (
            v.doctor.full_name if v.doctor else
            v.pharmacy.name if v.pharmacy else '—'
        )
        from django.urls import reverse
        visits_json_list.append({
            'day':      v.planned_date.date().day,
            'pk':       v.pk,
            'type':     v.visit_type,
            'target':   target,
            'employee': v.employee.get_full_name() or v.employee.username,
            'emp_id':   v.employee_id,
            'time':     v.planned_date.strftime('%H:%M'),
            'status':   v.status,
            'url':      reverse('visit_detail', args=[v.pk]),
            'edit_url': reverse('visit_edit', args=[v.pk]),
            'color':    emp_colors[v.employee_id],
        })

    # Сетка календаря
    cal = calendar.monthcalendar(year, month)

    MONTHS_RU = ['','Январь','Февраль','Март','Апрель','Май','Июнь',
                 'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь']

    employees = _get_visible_reps(request.user) if not user_is_employee(request.user) else []

    # Список сотрудников с цветами для легенды
    emp_legend = [
        {
            'pk':    emp_id,
            'name':  next((v['employee'] for v in visits_json_list if v['emp_id'] == emp_id), ''),
            'color': color,
        }
        for emp_id, color in emp_colors.items()
    ]

    return render(request, 'crm/calendar.html', {
        'year': year, 'month': month,
        'month_name': MONTHS_RU[month],
        'today': today,
        'cal': cal,
        'visits_json': json.dumps(visits_json_list, ensure_ascii=False),
        'emp_colors_json': json.dumps(emp_colors),
        'emp_legend': emp_legend,
        'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month,
        'employees': employees,
        'filter_emp': filter_emp or '',
        'is_employee': user_is_employee(request.user),
    })


# ─── helpers ────────────────────────────────────────────────────────────────

def user_is_employee(user):
    """Обычный сотрудник (не менеджер, не босс)."""
    return user.role in ['med_rep', 'warehouse', 'accountant', 'analyst']


def _get_visible_reps(user):
    """Список сотрудников-med_rep, которых может выбирать/видеть user."""
    if user.is_boss():
        return User.objects.filter(role='med_rep')
    if user.is_manager():
        return User.objects.filter(role='med_rep', manager=user)
    return User.objects.filter(pk=user.pk)
