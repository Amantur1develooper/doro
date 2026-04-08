from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
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
    return render(request, 'crm/doctors_list.html', {
        'doctors': doctors, 'regions': regions, 'reps': reps, 'search': search,
        'is_employee': user_is_employee(request.user),
    })


@login_required
def doctor_detail(request, pk):
    doctor = get_object_or_404(Doctor, pk=pk)
    # Доступ: boss и manager видят всех, сотрудник — только своего
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

        d.save()
        messages.success(request, f'Врач «{d.full_name}» добавлен')
        return redirect('doctors_list')
    return render(request, 'crm/doctor_form.html', {
        'regions': regions, 'reps': reps, 'is_employee': is_emp,
    })


@login_required
def pharmacies_list(request):
    pharmacies = Pharmacy.objects.select_related('region', 'representative')
    region_id = request.GET.get('region')
    search = request.GET.get('q', '')

    # Иерархия
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
    # Доступ
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
        'status_choices': Visit.STATUS_CHOICES
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
    return render(request, 'crm/visit_detail.html', {'visit': visit})


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
