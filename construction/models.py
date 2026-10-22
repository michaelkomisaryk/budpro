from decimal import Decimal
from functools import cached_property

from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Count, DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

from .access import is_director
from .validators import validate_phone, validate_quarter_hour

ZERO = Decimal("0")
MONEY = DecimalField(max_digits=18, decimal_places=2)


class ProjectQuerySet(models.QuerySet):
    """Проєкти з підрахованими сумами однією вибіркою (без N+1 у списках)."""

    def with_totals(self):
        def per_project(model, expression):
            return Subquery(model.objects.filter(project=OuterRef("pk")).order_by().values("project")
                            .annotate(t=expression).values("t"))

        return self.annotate(
            spent_total=Coalesce(per_project(Expense, Sum("amount")), Value(ZERO), output_field=MONEY),
            materials_total=Coalesce(per_project(Material, Sum(F("quantity") * F("unit_price"), output_field=MONEY)),
                                     Value(ZERO), output_field=MONEY),
            tasks_total=Coalesce(per_project(Task, Count("pk")), Value(0)),
            tasks_done=Coalesce(per_project(Task, Count("pk", filter=Q(status="done"))), Value(0)),
        )


class Project(models.Model):
    """Будівельний проєкт."""

    class Status(models.TextChoices):
        PLANNED = "planned", "Запланований"
        ACTIVE = "active", "Активний"
        COMPLETED = "completed", "Завершений"

    name = models.CharField("Назва", max_length=200)
    address = models.CharField("Адреса будівництва", max_length=255)
    description = models.TextField("Опис", blank=True)
    budget = models.DecimalField("Бюджет, ₴", max_digits=14, decimal_places=2,
                                 validators=[MinValueValidator(0)])
    start_date = models.DateField("Дата початку")
    end_date = models.DateField("Планова дата завершення")
    status = models.CharField("Статус", max_length=12, choices=Status.choices, default=Status.PLANNED)
    # PROTECT: акаунт директора з проєктами не можна видалити - фінансові дані не повинні зникнути разом із ним
    owner = models.ForeignKey(User, verbose_name="Власник (директор)", on_delete=models.PROTECT,
                              related_name="projects")
    created_at = models.DateTimeField("Створено", auto_now_add=True)

    objects = ProjectQuerySet.as_manager()

    class Meta:
        verbose_name = "Проєкт"
        verbose_name_plural = "Проєкти"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="uniq_project_owner_name",
                                    violation_error_message="У вас уже є проєкт з такою назвою."),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("construction:project_detail", args=[self.pk])

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "Дата завершення не може бути раніше дати початку."})

    # ----- розрахунки бюджету (беруться лише з витрат) -----
    @cached_property
    def spent(self):
        if hasattr(self, "spent_total"):  # значення вже пораховане в with_totals()
            return self.spent_total
        return self.expenses.aggregate(total=Sum("amount"))["total"] or ZERO

    @property
    def remaining(self):
        return self.budget - self.spent

    @property
    def budget_percent(self):
        """Реальний відсоток використаного бюджету (може бути більшим за 100)."""
        if self.budget == 0:
            return 100 if self.spent > 0 else 0
        return int(round(self.spent / self.budget * 100))

    @property
    def budget_bar(self):
        """Відсоток для індикатора: не більше 100."""
        return min(self.budget_percent, 100)

    @property
    def over_budget(self):
        return self.spent > self.budget

    # ----- матеріали рахуються окремо і до витрат не додаються -----
    @cached_property
    def materials_cost(self):
        if hasattr(self, "materials_total"):
            return self.materials_total
        total = self.materials.aggregate(
            total=Sum(F("quantity") * F("unit_price"), output_field=DecimalField(max_digits=18, decimal_places=2)))
        return total["total"] or ZERO

    # ----- прогрес і терміни -----
    @cached_property
    def progress(self):
        if hasattr(self, "tasks_total"):
            total, done = self.tasks_total, self.tasks_done
        else:
            total = self.tasks.count()
            done = self.tasks.filter(status=Task.Status.DONE).count()
        return int(round(done * 100 / total)) if total else 0

    @property
    def days_left(self):
        return (self.end_date - timezone.localdate()).days

    @property
    def is_overdue(self):
        return self.status != self.Status.COMPLETED and self.end_date < timezone.localdate()


class Task(models.Model):
    """Завдання в межах проєкту."""

    class Status(models.TextChoices):
        PENDING = "pending", "Очікує"
        IN_PROGRESS = "in_progress", "У роботі"
        DONE = "done", "Виконано"

    project = models.ForeignKey(Project, verbose_name="Проєкт", on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField("Назва завдання", max_length=200)
    description = models.TextField("Опис", blank=True)
    assignee = models.ForeignKey("Worker", verbose_name="Виконавець", on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name="tasks")
    due_date = models.DateField("Дата завершення")
    status = models.CharField("Статус", max_length=12, choices=Status.choices, default=Status.PENDING)
    materials = models.ManyToManyField("Material", verbose_name="Матеріали для завдання", blank=True,
                                       related_name="tasks")
    created_at = models.DateTimeField("Створено", auto_now_add=True)

    class Meta:
        verbose_name = "Завдання"
        verbose_name_plural = "Завдання"
        ordering = ["due_date"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("construction:task_detail", args=[self.pk])

    def clean(self):
        errors = {}
        if self.project_id and self.due_date and self.due_date < self.project.start_date:
            errors["due_date"] = "Термін завдання не може бути раніше початку проєкту."
        if self.project_id and self.assignee_id and self.assignee.project_id != self.project_id:
            errors["assignee"] = ("Виконавець має бути прикріплений до цього проєкту "
                                  "(змініть проєкт працівника на сторінці «Працівники»).")
        if errors:
            raise ValidationError(errors)

    @property
    def is_overdue(self):
        return self.status != self.Status.DONE and self.due_date < timezone.localdate()


class Worker(models.Model):
    """Працівник, який може бути прикріплений до проєкту."""

    class Position(models.TextChoices):
        MANAGER = "manager", "Керівник проєкту"
        ENGINEER = "engineer", "Інженер"
        FOREMAN = "foreman", "Прораб"
        BUILDER = "builder", "Будівельник"
        ELECTRICIAN = "electrician", "Електрик"
        PLUMBER = "plumber", "Сантехнік"
        PAINTER = "painter", "Маляр"
        OTHER = "other", "Інша"

    first_name = models.CharField("Ім'я", max_length=100)
    last_name = models.CharField("Прізвище", max_length=100)
    position = models.CharField("Посада", max_length=20, choices=Position.choices, default=Position.BUILDER)
    phone = models.CharField("Телефон", max_length=20, validators=[validate_phone])
    project = models.ForeignKey(Project, verbose_name="Проєкт", on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="workers")
    hourly_rate = models.DecimalField("Ставка, ₴/год", max_digits=8, decimal_places=2, default=0,
                                      validators=[MinValueValidator(0)])
    user = models.OneToOneField(User, verbose_name="Акаунт для входу", on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="worker_profile")
    # PROTECT: як і для проєкту - власника з працівниками не можна видалити випадково
    owner = models.ForeignKey(User, verbose_name="Власник (директор)", on_delete=models.PROTECT,
                              related_name="workers_owned")
    created_at = models.DateTimeField("Створено", auto_now_add=True)

    class Meta:
        verbose_name = "Працівник"
        verbose_name_plural = "Працівники"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.full_name

    def get_absolute_url(self):
        return reverse("construction:worker_detail", args=[self.pk])

    def delete(self, *args, **kwargs):
        """Разом із працівником видаляється його акаунт (але ніколи акаунт директора)."""
        user = self.user
        result = super().delete(*args, **kwargs)
        if user and not is_director(user):
            user.delete()
        return result

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def initials(self):
        return (self.first_name[:1] + self.last_name[:1]).upper()

    @property
    def tone(self):
        return sum(map(ord, self.full_name)) % 5


class Material(models.Model):
    """Облік матеріалів проєкту (кількість і вартість). Це не фінансові витрати."""

    class Unit(models.TextChoices):
        PCS = "pcs", "шт."
        KG = "kg", "кг"
        TON = "t", "т"
        M = "m", "м"
        M2 = "m2", "м²"
        M3 = "m3", "м³"
        L = "l", "л"

    name = models.CharField("Назва матеріалу", max_length=200)
    quantity = models.DecimalField("Кількість", max_digits=12, decimal_places=2,
                                   validators=[MinValueValidator(Decimal("0.01"))])
    unit = models.CharField("Одиниця виміру", max_length=5, choices=Unit.choices, default=Unit.PCS)
    unit_price = models.DecimalField("Ціна за одиницю, ₴", max_digits=12, decimal_places=2,
                                     validators=[MinValueValidator(0)])
    project = models.ForeignKey(Project, verbose_name="Проєкт", on_delete=models.CASCADE, related_name="materials")
    created_at = models.DateTimeField("Створено", auto_now_add=True)

    class Meta:
        verbose_name = "Матеріал"
        verbose_name_plural = "Матеріали"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("construction:material_detail", args=[self.pk])

    @property
    def cost(self):
        return self.quantity * self.unit_price


class CatalogItem(models.Model):
    """Каталог матеріалів: стандартні та власні позиції, з яких можна швидко вибирати матеріал."""

    name = models.CharField("Назва", max_length=200)
    unit = models.CharField("Одиниця виміру", max_length=5, choices=Material.Unit.choices, default=Material.Unit.PCS)
    unit_price = models.DecimalField("Ціна за одиницю, ₴", max_digits=12, decimal_places=2,
                                     validators=[MinValueValidator(0)])
    is_custom = models.BooleanField("Власна позиція", default=True)
    created_at = models.DateTimeField("Створено", auto_now_add=True)

    class Meta:
        verbose_name = "Позиція каталогу"
        verbose_name_plural = "Каталог матеріалів"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["name", "unit"], name="uniq_catalog_name_unit",
                                    violation_error_message="Така позиція (назва й одиниця виміру) вже є в каталозі."),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("construction:catalog_detail", args=[self.pk])


class Expense(models.Model):
    """Фактична фінансова витрата проєкту. Саме вони враховуються в контролі бюджету."""

    class Category(models.TextChoices):
        MATERIALS = "materials", "Матеріали"
        SALARY = "salary", "Зарплата"
        EQUIPMENT = "equipment", "Обладнання"
        TRANSPORT = "transport", "Транспорт"
        OTHER = "other", "Інше"

    project = models.ForeignKey(Project, verbose_name="Проєкт", on_delete=models.CASCADE, related_name="expenses")
    title = models.CharField("Назва витрати", max_length=200)
    category = models.CharField("Категорія", max_length=12, choices=Category.choices, default=Category.OTHER)
    amount = models.DecimalField("Сума, ₴", max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    date = models.DateField("Дата", default=timezone.localdate)
    description = models.TextField("Опис", blank=True)
    created_at = models.DateTimeField("Створено", auto_now_add=True)

    class Meta:
        verbose_name = "Витрата"
        verbose_name_plural = "Витрати"
        ordering = ["-date", "-id"]
        permissions = [("view_finance_reports", "Може переглядати фінансові звіти")]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("construction:expense_detail", args=[self.pk])


class WorkLog(models.Model):
    """Відпрацьовані години працівника по завданню. З них рахується зарплата."""

    worker = models.ForeignKey(Worker, verbose_name="Працівник", on_delete=models.CASCADE, related_name="logs")
    task = models.ForeignKey(Task, verbose_name="Завдання", on_delete=models.SET_NULL,
                             null=True, related_name="logs")
    date = models.DateField("Дата", default=timezone.localdate)
    hours = models.DecimalField("Години", max_digits=5, decimal_places=2,
                                validators=[MinValueValidator(Decimal("0.25")), MaxValueValidator(24), validate_quarter_hour])
    comment = models.CharField("Що зроблено", max_length=255, blank=True)
    rate = models.DecimalField("Ставка на момент запису, ₴/год", max_digits=8, decimal_places=2, default=0)
    created_at = models.DateTimeField("Створено", auto_now_add=True)

    class Meta:
        verbose_name = "Запис про години"
        verbose_name_plural = "Табель (години)"
        ordering = ["-date", "-id"]
        permissions = [("manage_payroll", "Може керувати зарплатами та табелем")]

    def __str__(self):
        return f"{self.worker} · {self.date} · {self.hours} год"

    def get_absolute_url(self):
        return reverse("construction:timesheet_detail", args=[self.pk])

    def clean(self):
        errors = {}
        if self.date and self.date > timezone.localdate():
            errors["date"] = "Не можна вносити години наперед."
        if self.task_id and self.worker_id and self.task.assignee_id != self.worker_id:
            errors["task"] = "Це завдання призначене іншому працівнику."
        if self.worker_id and self.date and self.hours:
            others = (WorkLog.objects.filter(worker_id=self.worker_id, date=self.date)
                      .exclude(pk=self.pk).aggregate(total=Sum("hours"))["total"] or ZERO)
            if others + self.hours > 24:
                errors["hours"] = "За добу не можна вносити більше 24 годин."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # ставка фіксується під час створення запису: зміна ставки не перераховує минулі місяці
        if self._state.adding and not self.rate:
            self.rate = self.worker.hourly_rate
        super().save(*args, **kwargs)

    @property
    def pay(self):
        return self.hours * self.rate
