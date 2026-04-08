from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('users/', views.users_list, name='users_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:pk>/', views.employee_card, name='employee_card'),
    path('users/<int:pk>/set-plan/', views.set_employee_plan, name='set_employee_plan'),
    path('users/<int:pk>/set-salary/', views.set_salary_percent, name='set_salary_percent'),
]
