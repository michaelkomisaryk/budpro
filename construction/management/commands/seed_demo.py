from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from construction.access import WORKER_GROUP, sync_roles
from construction.models import Expense, Material, Project, Task, WorkLog, Worker


class Command(BaseCommand):
    help = ("Необов'язково: додає демонстраційні дані. Директор: admin / admin12345 (суперкористувач), "
            "другий директор: director2 / director12345 (бачить лише свої дані). "
            "Працівники: логіни sklyar, koval, melnyk, boyko... / пароль worker12345")

    def handle(self, *args, **options):
        director_group = sync_roles()
        worker_group = director_group.__class__.objects.get(name=WORKER_GROUP)

        # директор 1: користувач admin створюється або, якщо вже є, отримує пароль admin12345
        admin, _ = User.objects.get_or_create(username="admin")
        admin.is_staff = True
        admin.is_superuser = True
        admin.first_name, admin.last_name = "Олександр", "Басюк"
        admin.set_password("admin12345")
        admin.save()
        admin.groups.add(director_group)

        # директор 2: звичайний директор (група «Директор» без прав суперкористувача)
        director2, _ = User.objects.get_or_create(username="director2")
        director2.first_name, director2.last_name = "Ірина", "Левченко"
        director2.email = "levchenko@example.com"
        director2.set_password("director12345")
        director2.save()
        director2.groups.add(director_group)

        if Project.objects.exists():
            self.stdout.write("Дані вже існують, нічого не додано (admin / admin12345, director2 / director12345 готові).")
            return

        today = timezone.localdate()

        def day(n):
            return today + timedelta(days=n)

        p1 = Project.objects.create(
            name="Житловий будинок на вул. Зеленій, 12", address="м. Львів, вул. Зелена, 12",
            description="Триповерховий житловий будинок з цегляними стінами.",
            budget=Decimal("250000"), start_date=day(-70), end_date=day(120), status="active", owner=admin)
        p2 = Project.objects.create(
            name="Офісний центр, вул. Городоцька, 48", address="м. Львів, вул. Городоцька, 48",
            description="Чотириповерховий офісний центр.",
            budget=Decimal("1200000"), start_date=day(-110), end_date=day(200), status="active", owner=admin)
        p3 = Project.objects.create(
            name="Склад-ангар, с. Рудне", address="Львівська обл., с. Рудне",
            budget=Decimal("400000"), start_date=day(-220), end_date=day(-20), status="completed", owner=admin)
        Project.objects.create(
            name="Котеджне містечко «Липки», 2 черга", address="смт Брюховичі, Львівська обл.",
            budget=Decimal("3500000"), start_date=day(30), end_date=day(300), status="planned", owner=admin)

        # працівники: ім'я, прізвище, посада, телефон, проєкт, ставка грн/год, логін
        people = [
            ("Олександр", "Басюк", "manager", "+380671234567", p1, "250", "basyuk"),
            ("Іван", "Скляр", "foreman", "+380501112233", p1, "220", "sklyar"),
            ("Петро", "Коваль", "builder", "+380931234000", p1, "160", "koval"),
            ("Марія", "Шевченко", "manager", "+380672223344", p2, "250", "shevchenko"),
            ("Олена", "Мельник", "engineer", "+380501234567", p2, "230", "melnyk"),
            ("Андрій", "Бойко", "electrician", "+380633334455", p2, "190", "boyko"),
            ("Василь", "Гнатюк", "builder", "+380974445566", None, "150", ""),
        ]
        w = {}
        for first, last, position, phone, project, rate, login in people:
            user = None
            if login:
                user = User(username=login, first_name=first, last_name=last)
                user.set_password("worker12345")
                user.save()
                user.groups.add(worker_group)
            w[last] = Worker.objects.create(first_name=first, last_name=last, position=position, phone=phone,
                                            project=project, hourly_rate=Decimal(rate), user=user, owner=admin)

        # завдання: проєкт, назва, виконавець, термін, статус
        tasks = [
            (p1, "Земляні роботи", "Коваль", day(-45), "done"), (p1, "Фундамент", "Скляр", day(-5), "in_progress"),
            (p1, "Зведення стін", "Коваль", day(50), "pending"), (p1, "Покрівля", "Скляр", day(90), "pending"),
            (p2, "Проєктна документація", "Мельник", day(-75), "done"), (p2, "Нульовий цикл", "Бойко", day(-35), "done"),
            (p2, "Монтаж перекриття 2 поверху", "Бойко", day(6), "in_progress"),
            (p2, "Каркас будівлі", "Мельник", day(60), "in_progress"), (p2, "Фасадні роботи", "Бойко", day(130), "pending"),
            (p3, "Фундаментна плита", "", day(-170), "done"), (p3, "Металевий каркас і покрівля", "", day(-30), "done"),
        ]
        made = []
        for project, title, who, due, status in tasks:
            made.append(Task.objects.create(project=project, title=title, due_date=due, status=status,
                                            assignee=w[who] if who else None))

        # табель: робочі дні за останні ~45 днів по завданню «у роботі» (або виконаному)
        for worker in w.values():
            mine = [t for t in made if t.assignee_id == worker.id]
            if not mine:
                continue
            task = next((t for t in mine if t.status == "in_progress"), mine[0])
            for offset in range(-45, 1):
                d = day(offset)
                if d.weekday() < 5:
                    WorkLog.objects.create(worker=worker, task=task, date=d, hours=Decimal("8" if offset % 2 else "7"),
                                           comment="Роботи за планом")

        materials = [
            (p1, "Цемент М500", "400", "pcs", "185"), (p1, "Цегла керамічна", "6000", "pcs", "11.50"),
            (p1, "Арматура Ø12", "1500", "m", "42"), (p2, "Бетон М300", "120", "m3", "2650"),
            (p2, "Пісок річковий", "90", "m3", "420"), (p3, "Профнастил С20", "900", "m2", "310"),
        ]
        for project, name, qty, unit, price in materials:
            Material.objects.create(project=project, name=name, quantity=Decimal(qty), unit=unit, unit_price=Decimal(price))

        expenses = [
            (p1, "Закупівля цементу та арматури", "materials", "137000", -40), (p1, "Оренда бетономішалки", "equipment", "9500", -25),
            (p1, "Доставка цегли", "transport", "7800", -8), (p1, "Закупівля цегли", "materials", "34500", -3),
            (p2, "Бетон М300 для нульового циклу", "materials", "318000", -80), (p2, "Оренда крану", "equipment", "210000", -50),
            (p2, "Арматура", "materials", "252000", -40), (p2, "Доставка матеріалів", "transport", "38000", -20),
            (p3, "Бетон та арматура", "materials", "122800", -190), (p3, "Профнастил", "materials", "279000", -80),
            (p3, "Зарплата бригаді", "salary", "40000", -60),
        ]
        for project, title, category, amount, offset in expenses:
            Expense.objects.create(project=project, title=title, category=category, amount=Decimal(amount), date=day(offset))

        # додаткові дані: достатньо записів для пагінації та демонстрації фільтрів
        more_tasks = [
            (p1, "Гідроізоляція фундаменту", "Коваль", day(10), "pending"), (p1, "Монтаж перекриття", "Скляр", day(70), "pending"),
            (p1, "Внутрішні інженерні мережі", "Коваль", day(100), "pending"), (p2, "Покрівельні роботи", "Мельник", day(150), "pending"),
            (p2, "Електромонтаж", "Бойко", day(160), "pending"), (p2, "Благоустрій території", "Мельник", day(190), "pending"),
        ]
        for project, title, who, due, status in more_tasks:
            made.append(Task.objects.create(project=project, title=title, due_date=due, status=status, assignee=w[who]))
        mats = {m.name: m for m in Material.objects.all()}
        for task in made:  # M2M: матеріали, потрібні для завдання (лише з того самого проєкту)
            names = {"Фундамент": ["Цемент М500", "Арматура Ø12"], "Зведення стін": ["Цегла керамічна", "Цемент М500"],
                     "Нульовий цикл": ["Бетон М300"], "Монтаж перекриття 2 поверху": ["Бетон М300", "Пісок річковий"]}.get(task.title, [])
            task.materials.add(*[mats[n] for n in names if n in mats and mats[n].project_id == task.project_id])
        extra_expenses = [
            (p1, "Оренда риштувань", "equipment", "12000", -30), (p1, "Паливо для техніки", "transport", "4300", -15),
            (p1, "Дрібний інструмент", "other", "2800", -12), (p2, "Оренда бетононасоса", "equipment", "46000", -45),
            (p2, "Закупівля шурупів і кріплень", "materials", "9700", -22), (p2, "Вивіз будівельного сміття", "transport", "8200", -10),
            (p2, "Охорона об'єкта", "other", "15500", -5),
        ]
        for project, title, category, amount, offset in extra_expenses:
            Expense.objects.create(project=project, title=title, category=category, amount=Decimal(amount), date=day(offset))

        # дані другого директора (ізольовані: admin їх теж бачить, але director2 не бачить даних admin)
        p5 = Project.objects.create(
            name="Дачний будинок, с. Підгірці", address="Львівська обл., с. Підгірці", budget=Decimal("180000"),
            start_date=day(-20), end_date=day(90), status="active", owner=director2)
        w5 = Worker.objects.create(first_name="Богдан", last_name="Ткач", position="builder", phone="+380991112233",
                                   project=p5, hourly_rate=Decimal("170"), owner=director2)
        Task.objects.create(project=p5, title="Закладання фундаменту", due_date=day(15), status="in_progress", assignee=w5)
        Expense.objects.create(project=p5, title="Закупівля бетону", category="materials", amount=Decimal("54000"), date=day(-10))

        self.stdout.write(self.style.SUCCESS(
            "Демо-дані додано.\nДиректор: admin / admin12345\nДиректор 2: director2 / director12345\nПрацівники: sklyar, koval, melnyk, boyko, basyuk, shevchenko / worker12345"))
