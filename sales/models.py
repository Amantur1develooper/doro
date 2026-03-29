from django.db import models
from django.conf import settings
from django.utils import timezone


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
    notes = models.TextField('Примечания', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Продажа'
        verbose_name_plural = 'Продажи'
        ordering = ['-date']

    def __str__(self):
        return f"Продажа #{self.pk} — {self.pharmacy} ({self.date})"

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
