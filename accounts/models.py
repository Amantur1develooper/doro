from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ('superadmin', 'Суперадминистратор'),
        ('director', 'Директор'),
        ('sales_manager', 'Руководитель отдела продаж'),
        ('med_rep', 'Медицинский представитель'),
        ('warehouse', 'Складской сотрудник'),
        ('accountant', 'Бухгалтер'),
        ('analyst', 'Аналитик'),
    ]
    role = models.CharField('Роль', max_length=20, choices=ROLE_CHOICES, default='med_rep')
    phone = models.CharField('Телефон', max_length=20, blank=True)
    region = models.ForeignKey('crm.Region', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Регион')
    avatar = models.ImageField('Фото', upload_to='avatars/', null=True, blank=True)

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    def is_director_or_above(self):
        return self.role in ['superadmin', 'director']

    def can_view_analytics(self):
        return self.role in ['superadmin', 'director', 'sales_manager', 'analyst']
