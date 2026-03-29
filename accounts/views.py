from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import User
from crm.models import Region


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
