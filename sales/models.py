from django.db import models
from django.conf import settings
from django.utils import timezone


class LegalEntity(models.Model):
    """Юридическое лицо — продавец (ИП, ОсОО, ОАО и т.д.)."""
    TYPE_CHOICES = [
        ('ip',   'ИП'),
        ('osoo', 'ОсОО'),
        ('oao',  'ОАО'),
        ('zao',  'ЗАО'),
        ('other','Другое'),
    ]
    name         = models.CharField('Полное наименование', max_length=300,
                                    help_text='Например: ИП «Арапова Арзихан Хакимовна»')
    entity_type  = models.CharField('Тип', max_length=10, choices=TYPE_CHOICES, default='ip')
    address      = models.CharField('Адрес', max_length=400, blank=True)
    bank         = models.CharField('Банк', max_length=300, blank=True)
    account      = models.CharField('Р/сч', max_length=100, blank=True)
    bik          = models.CharField('БИК', max_length=30, blank=True)
    inn          = models.CharField('ИНН', max_length=50, blank=True)
    certificate  = models.CharField('Свидетельство', max_length=200, blank=True,
                                    help_text='Например: №НС150153 от 24.04.2022')
    phone        = models.CharField('Телефон', max_length=50, blank=True)
    is_default   = models.BooleanField('По умолчанию', default=False)

    class Meta:
        verbose_name = 'Юридическое лицо'
        verbose_name_plural = 'Юридические лица'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Только одно юр. лицо может быть «по умолчанию»
        if self.is_default:
            LegalEntity.objects.exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class SalesPlan(models.Model):
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='Сотрудник'
    )
    month = models.IntegerField('Месяц')
    year = models.IntegerField('Год')
    plan_amount = models.DecimalField('План продаж', max_digits=14, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'План продаж'
        unique_together = ['employee', 'month', 'year']


class Sale(models.Model):
    STATUS_CHOICES = [
        ('pending', 'В обработке'),
        ('confirmed', 'Подтверждена'),
        ('shipped', 'Отгружена'),
        ('cancelled', 'Отменена'),
    ]
    date = models.DateField('Дата', default=timezone.now)
    legal_entity = models.ForeignKey(
        LegalEntity, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Юр. лицо (продавец)'
    )
    invoice_number = models.CharField('Номер накладной', max_length=50, blank=True)
    pharmacy = models.ForeignKey(
        'crm.Pharmacy', on_delete=models.SET_NULL, null=True, verbose_name='Аптека'
    )
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name='Сотрудник'
    )
    warehouse = models.ForeignKey(
        'warehouse.Warehouse', on_delete=models.SET_NULL, null=True, verbose_name='Склад'
    )
    status = models.CharField('Статус', max_length=15, choices=STATUS_CHOICES, default='pending')
    total_amount = models.DecimalField('Сумма', max_digits=14, decimal_places=2, default=0)
    total_cost = models.DecimalField('Себестоимость', max_digits=14, decimal_places=2, default=0)
    paid_amount = models.DecimalField('Оплачено', max_digits=14, decimal_places=2, default=0)
    receipt = models.FileField('Чек/Фото', upload_to='receipts/sales/', blank=True, null=True)
    notes = models.TextField('Примечания', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Продажа'
        verbose_name_plural = 'Продажи'
        ordering = ['-date']

    def __str__(self):
        return f"Продажа #{self.pk} — {self.pharmacy} ({self.date})"

    @property
    def remaining_debt(self):
        return max(0, self.total_amount - self.paid_amount)

    @property
    def margin(self):
        return self.total_amount - self.total_cost

    @property
    def margin_percent(self):
        if self.total_amount > 0:
            return round((self.margin / self.total_amount) * 100, 1)
        return 0


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items', verbose_name='Продажа')
    batch = models.ForeignKey(
        'warehouse.Batch', on_delete=models.SET_NULL, null=True, verbose_name='Партия'
    )
    quantity = models.IntegerField('Количество')
    sale_price = models.DecimalField('Цена продажи', max_digits=12, decimal_places=2)
    cost_price = models.DecimalField('Себестоимость', max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Строка продажи'

    @property
    def amount(self):
        return self.quantity * self.sale_price

    @property
    def margin(self):
        return (self.sale_price - self.cost_price) * self.quantity


class Payment(models.Model):
    """Запись об оплате долга аптеки."""
    pharmacy = models.ForeignKey(
        'crm.Pharmacy', on_delete=models.CASCADE,
        related_name='payments', verbose_name='Аптека'
    )
    amount = models.DecimalField('Сумма оплаты', max_digits=14, decimal_places=2)
    date = models.DateField('Дата', default=timezone.now)
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, verbose_name='Принял'
    )
    receipt = models.FileField('Чек/Фото', upload_to='receipts/payments/', blank=True, null=True)
    notes = models.TextField('Примечания', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Платёж'
        verbose_name_plural = 'Платежи'
        ordering = ['-date']

    def __str__(self):
        return f"Платёж {self.pharmacy} — {self.amount} ({self.date})"


class Invoice(models.Model):
    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, verbose_name='Продажа')
    invoice_number = models.CharField('Номер счет-фактуры', max_length=50)
    date = models.DateField('Дата')
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name='Выписал'
    )

    class Meta:
        verbose_name = 'Счет-фактура'
        verbose_name_plural = 'Счет-фактуры'

    def __str__(self):
        return f"СФ #{self.invoice_number}"
