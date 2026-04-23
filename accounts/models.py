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
    manager = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Руководитель', related_name='subordinates',
        limit_choices_to={'role': 'sales_manager'}
    )
    salary_percent = models.DecimalField(
        '% от продаж (ЗП)', max_digits=5, decimal_places=2, default=7,
        help_text='Процент от суммы продаж, начисляемый как зарплата'
    )

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    def is_boss(self):
        """Видит всё — суперадмин или директор."""
        return self.role in ['superadmin', 'director']

    def is_manager(self):
        """Менеджер — видит своих подчинённых."""
        return self.role == 'sales_manager'

    def is_director_or_above(self):
        return self.role in ['superadmin', 'director']

    def can_view_analytics(self):
        return self.role in ['superadmin', 'director', 'sales_manager', 'analyst']

    def get_visible_users(self):
        """Возвращает QuerySet пользователей, которых может видеть этот пользователь."""
        if self.is_boss():
            return User.objects.all()
        if self.is_manager():
            return User.objects.filter(manager=self)
        return User.objects.filter(pk=self.pk)


class UserLocation(models.Model):
    user      = models.OneToOneField(User, on_delete=models.CASCADE,
                                     related_name='location', verbose_name='Сотрудник')
    latitude  = models.DecimalField('Широта',  max_digits=9, decimal_places=6)
    longitude = models.DecimalField('Долгота', max_digits=9, decimal_places=6)
    address   = models.CharField('Адрес', max_length=300, blank=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    is_active  = models.BooleanField('Онлайн', default=True)

    class Meta:
        verbose_name = 'Геолокация'
        verbose_name_plural = 'Геолокации'

    def __str__(self):
        return f"{self.user} — {self.updated_at:%d.%m %H:%M}"
