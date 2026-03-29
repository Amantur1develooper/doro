from django.db import models
from django.conf import settings


class Region(models.Model):
    name = models.CharField('Название', max_length=100)
    code = models.CharField('Код', max_length=20, blank=True)

    class Meta:
        verbose_name = 'Регион'
        verbose_name_plural = 'Регионы'

    def __str__(self):
        return self.name


class Doctor(models.Model):
    full_name = models.CharField('ФИО', max_length=200)
    specialty = models.CharField('Специализация', max_length=100)
    institution = models.CharField('Медучреждение', max_length=200)
    phone = models.CharField('Телефон', max_length=20, blank=True)
    address = models.CharField('Адрес', max_length=300, blank=True)
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, verbose_name='Регион')
    representative = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Представитель', related_name='assigned_doctors'
    )
    notes = models.TextField('Заметки', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Врач'
        verbose_name_plural = 'Врачи'

    def __str__(self):
        return f"{self.full_name} — {self.specialty}"


class Pharmacy(models.Model):
    name = models.CharField('Название аптеки', max_length=200)
    address = models.CharField('Адрес', max_length=300)
    contact_person = models.CharField('Контактное лицо', max_length=200, blank=True)
    phone = models.CharField('Телефон', max_length=20, blank=True)
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, verbose_name='Регион')
    representative = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Сотрудник', related_name='assigned_pharmacies'
    )
    debt = models.DecimalField('Задолженность', max_digits=14, decimal_places=2, default=0)
    notes = models.TextField('Заметки', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Аптека'
        verbose_name_plural = 'Аптеки'

    def __str__(self):
        return self.name


class Visit(models.Model):
    STATUS_CHOICES = [
        ('planned', 'Запланирован'),
        ('done', 'Выполнен'),
        ('cancelled', 'Отменён'),
        ('postponed', 'Перенесён'),
    ]
    TYPE_CHOICES = [
        ('doctor', 'Врач'),
        ('pharmacy', 'Аптека'),
    ]
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='Сотрудник'
    )
    visit_type = models.CharField('Тип визита', max_length=10, choices=TYPE_CHOICES)
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Врач')
    pharmacy = models.ForeignKey(Pharmacy, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Аптека')
    status = models.CharField('Статус', max_length=15, choices=STATUS_CHOICES, default='planned')
    planned_date = models.DateTimeField('Плановая дата')
    actual_date = models.DateTimeField('Фактическая дата', null=True, blank=True)
    latitude = models.DecimalField('Широта', max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField('Долгота', max_digits=9, decimal_places=6, null=True, blank=True)
    comment = models.TextField('Комментарий', blank=True)
    result = models.TextField('Результат', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Визит'
        verbose_name_plural = 'Визиты'
        ordering = ['-planned_date']

    def __str__(self):
        target = self.doctor or self.pharmacy
        return f"Визит {self.employee} → {target} ({self.get_status_display()})"


class VisitPhoto(models.Model):
    visit = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='photos')
    photo = models.ImageField('Фото', upload_to='visit_photos/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Фотоотчет'


class VisitAudio(models.Model):
    visit = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='audios')
    audio = models.FileField('Аудиозапись', upload_to='visit_audio/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Аудиозапись'


class VisitPlan(models.Model):
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='Сотрудник'
    )
    month = models.IntegerField('Месяц')
    year = models.IntegerField('Год')
    planned_visits = models.IntegerField('План визитов', default=0)

    class Meta:
        verbose_name = 'План визитов'
        unique_together = ['employee', 'month', 'year']

    def __str__(self):
        return f"План {self.employee} {self.month}/{self.year}: {self.planned_visits}"
