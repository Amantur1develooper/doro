from django.db import models
from django.conf import settings
from django.utils import timezone


class Warehouse(models.Model):
    name = models.CharField('Название', max_length=200)
    address = models.CharField('Адрес', max_length=300, blank=True)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Менеджер'
    )

    class Meta:
        verbose_name = 'Склад'
        verbose_name_plural = 'Склады'

    def __str__(self):
        return self.name


class ProductCategory(models.Model):
    name = models.CharField('Название', max_length=100)

    class Meta:
        verbose_name = 'Категория товара'
        verbose_name_plural = 'Категории товаров'

    def __str__(self):
        return self.name


class Product(models.Model):
    STATUS_CHOICES = [
        ('in_stock', 'В наличии'),
        ('low', 'Мало'),
        ('out', 'Отсутствует'),
        ('expiring', 'Срок подходит к концу'),
        ('expired', 'Просрочен'),
    ]
    name = models.CharField('Наименование', max_length=200)
    international_name = models.CharField('Международное название', max_length=200, blank=True)
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, verbose_name='Категория')
    form = models.CharField('Форма выпуска', max_length=100, blank=True)
    dosage = models.CharField('Дозировка', max_length=100, blank=True)
    manufacturer = models.CharField('Производитель', max_length=200, blank=True)
    sku = models.CharField('Артикул/SKU', max_length=100, unique=True)
    unit = models.CharField('Единица', max_length=20, default='шт')
    purchase_price = models.DecimalField('Закупочная цена', max_digits=12, decimal_places=2, default=0)
    cost_price = models.DecimalField('Себестоимость', max_digits=12, decimal_places=2, default=0)
    sale_price = models.DecimalField('Отпускная цена', max_digits=12, decimal_places=2, default=0)
    notes = models.TextField('Примечания', blank=True)

    class Meta:
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def margin(self):
        if self.sale_price and self.cost_price:
            return self.sale_price - self.cost_price
        return 0

    @property
    def margin_percent(self):
        if self.sale_price and self.cost_price and self.sale_price > 0:
            return round((self.margin / self.sale_price) * 100, 1)
        return 0


class Batch(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='batches', verbose_name='Товар')
    batch_number = models.CharField('Серия/партия', max_length=100)
    expiry_date = models.DateField('Срок годности')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, verbose_name='Склад')
    quantity = models.IntegerField('Количество', default=0)
    purchase_price = models.DecimalField('Закупочная цена', max_digits=12, decimal_places=2, default=0)
    received_date = models.DateField('Дата прихода', default=timezone.now)

    class Meta:
        verbose_name = 'Партия'
        verbose_name_plural = 'Партии'

    def __str__(self):
        return f"{self.product.name} — {self.batch_number} (до {self.expiry_date})"

    @property
    def is_expiring(self):
        from datetime import date, timedelta
        return self.expiry_date <= date.today() + timedelta(days=90)

    @property
    def is_expired(self):
        from datetime import date
        return self.expiry_date < date.today()


class StockMovement(models.Model):
    TYPE_CHOICES = [
        ('in', 'Приход'),
        ('out', 'Расход'),
        ('move', 'Перемещение'),
        ('return', 'Возврат'),
        ('writeoff', 'Списание'),
        ('inventory', 'Инвентаризация'),
    ]
    movement_type = models.CharField('Тип', max_length=15, choices=TYPE_CHOICES)
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, verbose_name='Партия')
    warehouse_from = models.ForeignKey(
        Warehouse, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Откуда', related_name='movements_out'
    )
    warehouse_to = models.ForeignKey(
        Warehouse, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Куда', related_name='movements_in'
    )
    quantity = models.IntegerField('Количество')
    price = models.DecimalField('Цена', max_digits=12, decimal_places=2, default=0)
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name='Сотрудник'
    )
    notes = models.TextField('Примечания', blank=True)
    date = models.DateTimeField('Дата', default=timezone.now)

    class Meta:
        verbose_name = 'Движение товара'
        verbose_name_plural = 'Движения товаров'
        ordering = ['-date']

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.batch.product.name} × {self.quantity}"
