from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from crm.models import Region, Doctor, Pharmacy, Visit
from warehouse.models import Warehouse, ProductCategory, Product, Batch
from sales.models import Sale, SaleItem
from datetime import date, timedelta, datetime
import random

User = get_user_model()


class Command(BaseCommand):
    help = 'Загрузка тестовых данных для демонстрации'

    def handle(self, *args, **options):
        self.stdout.write('🌱 Создание тестовых данных...')

        # Regions
        regions = []
        for name in ['Бишкек', 'Ош', 'Чуйская область', 'Иссык-Кульская область', 'Нарынская область']:
            r, _ = Region.objects.get_or_create(name=name)
            regions.append(r)
        self.stdout.write('✅ Регионы созданы')

        # Superadmin
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin', password='admin123',
                first_name='Администратор', last_name='',
                role='superadmin', email='admin@dorolien.kg'
            )
        self.stdout.write('✅ Суперадмин: admin / admin123')

        # Director
        director, _ = User.objects.get_or_create(username='director', defaults={
            'first_name': 'Директор', 'last_name': 'Иванов',
            'role': 'director', 'region': regions[0]
        })
        director.set_password('demo123')
        director.save()

        # Sales manager
        mgr, _ = User.objects.get_or_create(username='manager', defaults={
            'first_name': 'Айбек', 'last_name': 'Усупов',
            'role': 'sales_manager', 'region': regions[0]
        })
        mgr.set_password('demo123')
        mgr.save()

        # Med reps
        reps = []
        rep_data = [
            ('rep1', 'Марат', 'Токтосунов', regions[0]),
            ('rep2', 'Динара', 'Асанова', regions[1]),
            ('rep3', 'Нурлан', 'Бекматов', regions[2]),
        ]
        for username, fn, ln, reg in rep_data:
            u, _ = User.objects.get_or_create(username=username, defaults={
                'first_name': fn, 'last_name': ln, 'role': 'med_rep', 'region': reg
            })
            u.set_password('demo123')
            u.save()
            reps.append(u)

        # Warehouse staff
        wh_staff, _ = User.objects.get_or_create(username='warehouse1', defaults={
            'first_name': 'Азамат', 'last_name': 'Жумалиев',
            'role': 'warehouse', 'region': regions[0]
        })
        wh_staff.set_password('demo123')
        wh_staff.save()
        self.stdout.write('✅ Пользователи созданы (пароль: demo123)')

        # Warehouses
        wh1, _ = Warehouse.objects.get_or_create(name='Главный склад Бишкек', defaults={'address': 'г. Бишкек, ул. Ленина 1', 'manager': wh_staff})
        wh2, _ = Warehouse.objects.get_or_create(name='Склад Ош', defaults={'address': 'г. Ош, ул. Масалиева 5', 'manager': wh_staff})
        warehouses = [wh1, wh2]
        self.stdout.write('✅ Склады созданы')

        # Categories
        cats = []
        for name in ['Антибиотики', 'Анальгетики', 'Витамины', 'Сердечно-сосудистые', 'Гастроэнтерология']:
            c, _ = ProductCategory.objects.get_or_create(name=name)
            cats.append(c)

        # Products
        products_data = [
            ('Амоксициллин', 'Amoxicillin', cats[0], 'Капсулы', '500мг', 'Биосинтез', 'AMX-500', 85, 90, 150),
            ('Парацетамол', 'Paracetamol', cats[1], 'Таблетки', '500мг', 'Дарница', 'PAR-500', 12, 15, 35),
            ('Витамин C', 'Ascorbic acid', cats[2], 'Таблетки', '250мг', 'ФармЛаб', 'VIT-C', 45, 50, 90),
            ('Эналаприл', 'Enalapril', cats[3], 'Таблетки', '10мг', 'Гедеон', 'ENA-10', 120, 130, 220),
            ('Омепразол', 'Omeprazole', cats[4], 'Капсулы', '20мг', 'Гексал', 'OMP-20', 95, 105, 180),
            ('Метронидазол', 'Metronidazole', cats[0], 'Таблетки', '250мг', 'Биосинтез', 'MTZ-250', 30, 35, 70),
            ('Ибупрофен', 'Ibuprofen', cats[1], 'Таблетки', '400мг', 'Польфарма', 'IBU-400', 55, 60, 110),
            ('Лоратадин', 'Loratadine', cats[2], 'Таблетки', '10мг', 'ФармЛаб', 'LOR-10', 40, 45, 85),
        ]
        products = []
        for name, iname, cat, form, dosage, mfr, sku, pp, cp, sp in products_data:
            p, _ = Product.objects.get_or_create(sku=sku, defaults={
                'name': name, 'international_name': iname, 'category': cat,
                'form': form, 'dosage': dosage, 'manufacturer': mfr,
                'purchase_price': pp, 'cost_price': cp, 'sale_price': sp
            })
            products.append(p)
        self.stdout.write('✅ Товары созданы')

        # Batches
        today = date.today()
        for product in products:
            for wh in warehouses:
                qty = random.randint(50, 500)
                exp = today + timedelta(days=random.randint(60, 730))
                batch_num = f"Б-{random.randint(10000,99999)}"
                b, created = Batch.objects.get_or_create(
                    product=product, warehouse=wh, batch_number=batch_num,
                    defaults={'expiry_date': exp, 'quantity': qty, 'purchase_price': product.purchase_price}
                )
        self.stdout.write('✅ Партии товаров созданы')

        # Doctors
        doctor_data = [
            ('Иванова Мария Петровна', 'Терапевт', 'ГКБ №1', regions[0]),
            ('Бекенов Алмаз Джумабекович', 'Кардиолог', 'Национальный центр кардиологии', regions[0]),
            ('Омурова Гульнара Бакытбековна', 'Педиатр', 'Детская больница №3', regions[1]),
            ('Сыдыков Максат Эркинович', 'Невролог', 'ОКБ г. Ош', regions[1]),
            ('Жамалова Айгерим', 'Гастроэнтеролог', 'ГКБ №4', regions[2]),
        ]
        doctors = []
        for fn, sp, inst, reg in doctor_data:
            d, _ = Doctor.objects.get_or_create(
                full_name=fn,
                defaults={'specialty': sp, 'institution': inst, 'region': reg,
                         'representative': random.choice(reps)}
            )
            doctors.append(d)

        # Pharmacies
        pharmacy_data = [
            ('Аптека Здоровье', 'ул. Чуй 145, Бишкек', 'Айгуль Мамытова', regions[0]),
            ('Фарм-Плюс', 'пр. Манас 22, Бишкек', 'Нурия Касымова', regions[0]),
            ('Аптека Народная', 'ул. Ленина 87, Ош', 'Руслан Осмонов', regions[1]),
            ('МедФарм', 'ул. Токтогула 12, Бишкек', 'Зина Алиева', regions[0]),
            ('Айболит', 'ул. Советская 34, Каракол', 'Бекзод Уралов', regions[3]),
        ]
        pharmacies = []
        for name, addr, contact, reg in pharmacy_data:
            p, _ = Pharmacy.objects.get_or_create(
                name=name,
                defaults={'address': addr, 'contact_person': contact, 'region': reg,
                         'representative': random.choice(reps),
                         'debt': random.randint(0, 50000)}
            )
            pharmacies.append(p)
        self.stdout.write('✅ Врачи и аптеки созданы')

        # Visits
        for i in range(20):
            rep = random.choice(reps)
            days_ago = random.randint(-30, 7)
            planned = datetime.now() + timedelta(days=days_ago)
            visit_type = random.choice(['doctor', 'pharmacy'])
            status = random.choice(['done', 'done', 'done', 'planned', 'cancelled'])
            v, _ = Visit.objects.get_or_create(
                employee=rep, planned_date=planned, visit_type=visit_type,
                defaults={
                    'doctor': random.choice(doctors) if visit_type == 'doctor' else None,
                    'pharmacy': random.choice(pharmacies) if visit_type == 'pharmacy' else None,
                    'status': status,
                    'comment': 'Плановый визит',
                    'result': 'Обсудили ассортимент' if status == 'done' else '',
                }
            )

        # Sales
        batches = list(Batch.objects.filter(quantity__gt=0)[:10])
        if batches:
            for i in range(10):
                pharmacy = random.choice(pharmacies)
                rep = random.choice(reps)
                days_ago = random.randint(0, 30)
                sale_date = today - timedelta(days=days_ago)
                sale = Sale.objects.create(
                    date=sale_date, pharmacy=pharmacy, employee=rep,
                    warehouse=wh1, status=random.choice(['confirmed', 'confirmed', 'pending']),
                    total_amount=0, total_cost=0
                )
                total_amount = 0
                total_cost = 0
                for _ in range(random.randint(2, 5)):
                    b = random.choice(batches)
                    qty = random.randint(10, 100)
                    SaleItem.objects.create(
                        sale=sale, batch=b, quantity=qty,
                        sale_price=b.product.sale_price,
                        cost_price=b.product.cost_price
                    )
                    total_amount += qty * b.product.sale_price
                    total_cost += qty * b.product.cost_price
                sale.total_amount = total_amount
                sale.total_cost = total_cost
                sale.save()
        self.stdout.write('✅ Продажи созданы')

        self.stdout.write(self.style.SUCCESS("""
╔══════════════════════════════════════╗
║  ✅ ТЕСТОВЫЕ ДАННЫЕ ЗАГРУЖЕНЫ!       ║
║                                      ║
║  Логины для входа:                   ║
║  admin / admin123 (суперадмин)       ║
║  director / demo123 (директор)       ║
║  manager / demo123 (рук. продаж)     ║
║  rep1 / demo123 (мед. представитель) ║
║  warehouse1 / demo123 (склад)        ║
╚══════════════════════════════════════╝
"""))
