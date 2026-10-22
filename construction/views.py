import calendar
import csv
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import DecimalField, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView

from .access import for_user, sync_roles
from .forms import (CatalogItemForm, ExpenseForm, MaterialForm, PeriodForm, ProfileForm, ProjectFilterForm,
                    ProjectForm, RegisterForm, TaskFilterForm, TaskForm, WorkLogForm, WorkerForm, style_fields,
                    PROJECT_SORTS)
from .mixins import (BaseCreateView, BaseDeleteView, BaseDetailView, BaseUpdateView, DirectorMixin, OwnedMixin,
                     OwnerOnCreateMixin, director_required, safe_next, worker_required)
from .models import ZERO, CatalogItem, Expense, Material, Project, Task, WorkLog, Worker

MONTHS = ["січ", "лют", "бер", "кві", "тра", "чер", "лип", "сер", "вер", "жов", "лис", "гру"]
MATERIAL_COST = Sum(F("quantity") * F("unit_price"), output_field=DecimalField(max_digits=18, decimal_places=2))
PAY = Sum(F("hours") * F("rate"), output_field=DecimalField(max_digits=14, decimal_places=2))
MONTH_NAMES = ["січень", "лютий", "березень", "квітень", "травень", "червень",
               "липень", "серпень", "вересень", "жовтень", "листопад", "грудень"]


# ---------------------------------------------------------------- допоміжні функції
def parse_month(value):
    """'2026-10' -> (2026, 10); якщо рядок некоректний - None."""
    try:
        year, month = (int(part) for part in value.split("-"))
        date(year, month, 1)
    except ValueError:
        return None
    return year, month


def get_month(request):
    """Місяць із параметра ?month=РРРР-ММ (за замовчуванням - поточний)."""
    parsed = parse_month(request.GET.get("month", ""))
    if parsed:
        return parsed
    today = timezone.localdate()
    return today.year, today.month


def month_info(year, month):
    return {"value": f"{year}-{month:02d}", "label": f"{MONTH_NAMES[month - 1]} {year}"}


def month_totals(logs):
    """(години, сума) по записах табеля."""
    data = logs.aggregate(total_hours=Sum("hours"), total_pay=PAY)
    return data["total_hours"] or ZERO, data["total_pay"] or ZERO


def salary_title(worker, year, month):
    return f"Зарплата: {worker.full_name}, {month:02d}.{year}"


def total(queryset, field="amount"):
    """Сума поля по queryset (0, якщо записів немає)."""
    return queryset.aggregate(t=Sum(field))["t"] or ZERO


def get_period(request):
    """Період із GET через форму PeriodForm: (форма, від, до). Некоректний період ігнорується."""
    form = PeriodForm(request.GET)
    if form.is_valid():
        return form, form.cleaned_data["date_from"], form.cleaned_data["date_to"]
    return form, None, None


def filter_period(expenses, date_from, date_to):
    if date_from:
        expenses = expenses.filter(date__gte=date_from)
    if date_to:
        expenses = expenses.filter(date__lte=date_to)
    return expenses


def by_category(expenses):
    """Витрати, згруповані за категоріями, з відсотками від загальної суми."""
    labels = dict(Expense.Category.choices)
    rows = expenses.order_by().values("category").annotate(total=Sum("amount")).order_by("-total")
    all_total = sum((r["total"] for r in rows), ZERO)
    return [
        {"key": r["category"], "label": labels[r["category"]], "total": r["total"],
         "percent": int(round(r["total"] * 100 / all_total)) if all_total else 0}
        for r in rows
    ]


def by_month(expenses):
    """Витрати за місяцями: словник {(рік, місяць): сума}."""
    rows = (expenses.order_by().annotate(month=TruncMonth("date")).values("month")
            .annotate(total=Sum("amount")).order_by("month"))
    return {(r["month"].year, r["month"].month): r["total"] for r in rows}


def month_rows(expenses):
    sums = by_month(expenses)
    return [{"label": f"{MONTHS[m - 1]} {y}", "total": t} for (y, m), t in sorted(sums.items())]


# ================================================================ реєстрація
class RegisterView(CreateView):
    """Реєстрація нового директора: створює акаунт, додає в групу «Директор» і одразу входить."""
    form_class = RegisterForm
    template_name = "registration/register.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("construction:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        user.groups.add(sync_roles())
        login(self.request, user)
        messages.success(self.request, "Акаунт створено. Ласкаво просимо до БудПроєкту!")
        return redirect("construction:dashboard")


# ================================================================ головна (function-based: зведення з кількох джерел)
@login_required
def dashboard(request):
    if not request.is_director:
        return redirect("construction:my_tasks")
    user = request.user
    projects = list(for_user(Project, user).with_totals())  # суми пораховано в одному запиті
    expenses = for_user(Expense, user)
    total_budget = sum((p.budget for p in projects), ZERO)
    total_spent = total(expenses)

    # останні 6 місяців (включно з поточним)
    today = timezone.localdate()
    months = []
    year, month = today.year, today.month
    for _ in range(6):
        months.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    months.reverse()
    sums = by_month(expenses.filter(date__gte=date(months[0][0], months[0][1], 1)))
    values = [sums.get(m, ZERO) for m in months]
    biggest = max(values)
    chart = [{"label": MONTHS[m - 1], "total": v, "height": int(v * 100 / biggest) if biggest else 0}
             for (y, m), v in zip(months, values)]

    unfinished = for_user(Task, user).exclude(status=Task.Status.DONE)
    context = {
        "projects_count": len(projects),
        "active_count": sum(p.status == Project.Status.ACTIVE for p in projects),
        "completed_count": sum(p.status == Project.Status.COMPLETED for p in projects),
        "total_budget": total_budget,
        "total_spent": total_spent,
        "total_remaining": total_budget - total_spent,
        "workers_count": for_user(Worker, user).count(),
        "unfinished_count": unfinished.count(),
        "recent_projects": projects[:5],
        "chart": chart,
        "chart_has_data": biggest > 0,
        "categories": by_category(expenses),
        "alerts": [p for p in projects if p.status != Project.Status.COMPLETED and p.budget_percent >= 90],
        "upcoming": unfinished.select_related("project").order_by("due_date")[:6],
    }
    return render(request, "construction/dashboard.html", context)


# ================================================================ проєкти (повний CRUD на Generic Views)
class ProjectListView(DirectorMixin, OwnedMixin, ListView):
    model = Project
    template_name = "construction/project_list.html"
    context_object_name = "projects"
    paginate_by = 8

    def get_queryset(self):
        projects = super().get_queryset().with_totals()
        self.filter_form = ProjectFilterForm(self.request.GET)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data["q"]:
                projects = projects.filter(Q(name__icontains=data["q"]) | Q(address__icontains=data["q"]))
            if data["status"]:
                projects = projects.filter(status=data["status"])
            ordering = PROJECT_SORTS.get(data["sort"], PROJECT_SORTS["new"])[0]
        else:
            ordering = PROJECT_SORTS["new"][0]
        return projects.order_by(ordering)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        context["filters_active"] = bool(self.request.GET.get("q") or self.request.GET.get("status"))
        return context


class ProjectDetailView(DirectorMixin, OwnedMixin, DetailView):
    model = Project
    template_name = "construction/project_detail.html"

    def get_queryset(self):
        return super().get_queryset().with_totals()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        context.update(
            tasks=project.tasks.select_related("assignee"),
            workers=project.workers.all(),
            materials=project.materials.all(),
            expenses=project.expenses.all(),
        )
        return context


class ProjectCreateView(OwnerOnCreateMixin, BaseCreateView):
    model = Project
    form_class = ProjectForm
    title = "Новий проєкт"
    back = "project_list"

    def get_success_url(self):
        # нову сторінку проєкту показуємо, якщо немає явної адреси повернення (next)
        return safe_next(self.request, self.object.get_absolute_url())


class ProjectUpdateView(BaseUpdateView):
    model = Project
    form_class = ProjectForm
    title = "Редагування проєкту"
    back = "project_list"

    def get_success_url(self):
        return safe_next(self.request, self.object.get_absolute_url())


class ProjectDeleteView(BaseDeleteView):
    model = Project
    title = "Видалити проєкт?"
    back = "project_list"
    text = ("Разом із проєктом буде видалено всі його завдання, матеріали та витрати. "
            "Працівники залишаться в системі, але стануть відкріпленими від проєкту.")


# ================================================================ завдання
class TaskListView(DirectorMixin, OwnedMixin, ListView):
    model = Task
    template_name = "construction/task_list.html"
    context_object_name = "tasks"
    paginate_by = 12

    def get_queryset(self):
        tasks = super().get_queryset().select_related("project", "assignee")
        self.filter_form = TaskFilterForm(self.request.GET, user=self.request.user)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data["q"]:
                tasks = tasks.filter(Q(title__icontains=data["q"]) | Q(description__icontains=data["q"]))
            if data["project"]:
                tasks = tasks.filter(project=data["project"])
            if data["assignee"]:
                tasks = tasks.filter(assignee=data["assignee"])
            if data["status"]:
                tasks = tasks.filter(status=data["status"])
        return tasks

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        keys = ("q", "project", "assignee", "status")
        context.update(filter_form=self.filter_form, filters_active=any(self.request.GET.get(k) for k in keys))
        return context


class TaskDetailView(BaseDetailView):
    model = Task
    back, edit, delete = "task_list", "task_edit", "task_delete"
    detail_fields = (
        ("Проєкт", "project"), ("Виконавець", "assignee"), ("Опис", "description"),
        ("Термін", "due_date"), ("Статус", "get_status_display"),
        ("Матеріали", lambda t: ", ".join(m.name for m in t.materials.all())),
    )


class TaskCreateView(BaseCreateView):
    model = Task
    form_class = TaskForm
    title = "Нове завдання"
    back = "task_list"
    initial_params = ("project",)


class TaskUpdateView(BaseUpdateView):
    model = Task
    form_class = TaskForm
    title = "Редагування завдання"
    back = "task_list"


class TaskDeleteView(BaseDeleteView):
    model = Task
    title = "Видалити завдання?"
    back = "task_list"


@director_required
@require_POST
def task_done(request, pk):
    """Дія через POST (function-based): позначає завдання виконаним."""
    task = get_object_or_404(for_user(Task, request.user), pk=pk)
    task.status = Task.Status.DONE
    task.save()
    messages.success(request, f"Завдання «{task.title}» позначено виконаним.")
    return redirect(safe_next(request, reverse("construction:task_list")))


# ================================================================ працівники
class WorkerListView(DirectorMixin, OwnedMixin, ListView):
    model = Worker
    template_name = "construction/worker_list.html"
    context_object_name = "workers"
    paginate_by = 12

    def get_queryset(self):
        workers = super().get_queryset().select_related("project", "user")
        self.q = self.request.GET.get("q", "").strip()
        self.position = self.request.GET.get("position", "")
        self.project_id = self.request.GET.get("project", "")
        if self.q:
            workers = workers.filter(Q(first_name__icontains=self.q) | Q(last_name__icontains=self.q))
        if self.position:
            workers = workers.filter(position=self.position)
        if self.project_id.isdigit():
            workers = workers.filter(project_id=self.project_id)
        return workers

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(q=self.q, position=self.position, project_id=self.project_id,
                       positions=Worker.Position.choices, projects=for_user(Project, self.request.user))
        return context


class WorkerDetailView(BaseDetailView):
    model = Worker
    back, edit, delete = "worker_list", "worker_edit", "worker_delete"
    detail_fields = (
        ("Посада", "get_position_display"), ("Телефон", "phone"), ("Проєкт", "project"),
        ("Ставка, ₴/год", "hourly_rate"), ("Логін для входу", lambda w: w.user.username if w.user else None),
    )

    def get_queryset(self):
        return super().get_queryset().select_related("project", "user")


class WorkerCreateView(OwnerOnCreateMixin, BaseCreateView):
    model = Worker
    form_class = WorkerForm
    title = "Новий працівник"
    back = "worker_list"
    initial_params = ("project",)


class WorkerUpdateView(BaseUpdateView):
    model = Worker
    form_class = WorkerForm
    title = "Редагування працівника"
    back = "worker_list"


class WorkerDeleteView(BaseDeleteView):
    model = Worker
    title = "Видалити працівника?"
    back = "worker_list"
    text = "Разом із працівником буде видалено його акаунт для входу та записи про відпрацьовані години."


# ================================================================ матеріали
class MaterialListView(DirectorMixin, OwnedMixin, ListView):
    model = Material
    template_name = "construction/material_list.html"
    context_object_name = "materials"
    paginate_by = 12

    def get_queryset(self):
        materials = super().get_queryset().select_related("project")
        self.q = self.request.GET.get("q", "").strip()
        self.project_id = self.request.GET.get("project", "")
        if self.q:
            materials = materials.filter(name__icontains=self.q)
        if self.project_id.isdigit():
            materials = materials.filter(project_id=self.project_id)
        return materials

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mine = for_user(Material, self.request.user)
        per_project = (mine.order_by().values("project_id", "project__name")
                       .annotate(total=MATERIAL_COST).order_by("project__name"))
        context.update(
            q=self.q, project_id=self.project_id, projects=for_user(Project, self.request.user),
            per_project=per_project,
            total_cost=self.object_list.aggregate(t=MATERIAL_COST)["t"] or ZERO,  # по всіх знайдених, а не лише по сторінці
        )
        return context


class MaterialDetailView(BaseDetailView):
    model = Material
    back, edit, delete = "material_list", "material_edit", "material_delete"
    detail_fields = (
        ("Проєкт", "project"), ("Кількість", "quantity"), ("Одиниця виміру", "get_unit_display"),
        ("Ціна за одиницю, ₴", "unit_price"), ("Вартість, ₴", "cost"),
        ("Використовується в завданнях", lambda m: ", ".join(t.title for t in m.tasks.all())),
    )

    def get_queryset(self):
        return super().get_queryset().select_related("project")


class MaterialCreateView(BaseCreateView):
    model = Material
    form_class = MaterialForm
    title = "Новий матеріал"
    back = "material_list"
    initial_params = ("project",)


class MaterialUpdateView(BaseUpdateView):
    model = Material
    form_class = MaterialForm
    title = "Редагування матеріалу"
    back = "material_list"


class MaterialDeleteView(BaseDeleteView):
    model = Material
    title = "Видалити матеріал?"
    back = "material_list"


# ---------------------------------------------------------------- каталог матеріалів (довідник, спільний для директорів)
class CatalogListView(DirectorMixin, ListView):
    model = CatalogItem
    template_name = "construction/material_catalog.html"
    context_object_name = "items"
    paginate_by = 15

    def get_queryset(self):
        self.q = self.request.GET.get("q", "").strip()
        items = super().get_queryset()
        return items.filter(name__icontains=self.q) if self.q else items

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.q
        return context


class CatalogDetailView(BaseDetailView):
    model = CatalogItem
    back, edit, delete = "material_catalog", "catalog_edit", "catalog_delete"
    detail_fields = (
        ("Одиниця виміру", "get_unit_display"), ("Ціна за одиницю, ₴", "unit_price"),
        ("Власна позиція", "is_custom"), ("Створено", "created_at"),
    )


class CatalogCreateView(BaseCreateView):
    model = CatalogItem
    form_class = CatalogItemForm
    title = "Нова позиція каталогу"
    back = "material_catalog"


class CatalogUpdateView(BaseUpdateView):
    model = CatalogItem
    form_class = CatalogItemForm
    title = "Редагування позиції каталогу"
    back = "material_catalog"


class CatalogDeleteView(BaseDeleteView):
    model = CatalogItem
    title = "Видалити позицію каталогу?"
    back = "material_catalog"
    text = "Матеріали, які вже додані до проєктів, не зміняться."


# ================================================================ витрати
class ExpenseListView(DirectorMixin, OwnedMixin, ListView):
    model = Expense
    template_name = "construction/expense_list.html"
    context_object_name = "expenses"
    paginate_by = 12

    def get_queryset(self):
        expenses = super().get_queryset().select_related("project")
        self.q = self.request.GET.get("q", "").strip()
        self.project_id = self.request.GET.get("project", "")
        self.category = self.request.GET.get("category", "")
        self.period_form, self.date_from, self.date_to = get_period(self.request)
        if self.q:
            expenses = expenses.filter(Q(title__icontains=self.q) | Q(description__icontains=self.q))
        if self.project_id.isdigit():
            expenses = expenses.filter(project_id=self.project_id)
        if self.category:
            expenses = expenses.filter(category=self.category)
        return filter_period(expenses, self.date_from, self.date_to)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        found = self.object_list  # усі знайдені витрати (без пагінації) - для підсумків
        context.update(
            q=self.q, project_id=self.project_id, category=self.category,
            date_from=self.date_from, date_to=self.date_to, period_form=self.period_form,
            projects=for_user(Project, self.request.user), categories=Expense.Category.choices,
            total=total(found), category_rows=by_category(found), month_rows=month_rows(found),
            filters_active=bool(self.q or self.project_id or self.category or self.date_from or self.date_to),
        )
        return context


class ExpenseDetailView(BaseDetailView):
    model = Expense
    back, edit, delete = "expense_list", "expense_edit", "expense_delete"
    detail_fields = (
        ("Проєкт", "project"), ("Категорія", "get_category_display"), ("Сума, ₴", "amount"),
        ("Дата", "date"), ("Опис", "description"),
    )

    def get_queryset(self):
        return super().get_queryset().select_related("project")


class ExpenseCreateView(BaseCreateView):
    model = Expense
    form_class = ExpenseForm
    title = "Нова витрата"
    back = "expense_list"
    initial_params = ("project",)


class ExpenseUpdateView(BaseUpdateView):
    model = Expense
    form_class = ExpenseForm
    title = "Редагування витрати"
    back = "expense_list"


class ExpenseDeleteView(BaseDeleteView):
    model = Expense
    title = "Видалити витрату?"
    back = "expense_list"


# ================================================================ звіти (function-based: розрахунки, експорт CSV)
def report_data(request):
    """Дані для сторінки звітів і для CSV (витрати фільтруються за періодом)."""
    period_form, date_from, date_to = get_period(request)
    period = filter_period(for_user(Expense, request.user), date_from, date_to)

    period_sums = {r["project"]: r["total"]
                   for r in period.order_by().values("project").annotate(total=Sum("amount"))}
    rows = []
    for project in for_user(Project, request.user).with_totals().order_by("name"):
        rows.append({"project": project, "spent": project.spent, "period": period_sums.get(project.id, ZERO)})
    for row in rows:
        # масштаб смуг окремий для кожного проєкту: видно співвідношення бюджету та витрат
        scale = max(row["project"].budget, row["spent"])
        row["budget_width"] = int(row["project"].budget * 100 / scale) if scale else 0
        row["spent_width"] = int(row["spent"] * 100 / scale) if scale else 0

    return {
        "date_from": date_from, "date_to": date_to, "period_form": period_form,
        "rows": rows,
        "top": sorted(rows, key=lambda r: r["spent"], reverse=True)[:5],
        "period_total": total(period),
        "period_count": period.count(),
        "category_rows": by_category(period),
        "month_rows": month_rows(period),
        "total_budget": sum((r["project"].budget for r in rows), ZERO),
        "total_spent": sum((r["spent"] for r in rows), ZERO),
    }


@director_required(perm="construction.view_finance_reports")
def report_list(request):
    return render(request, "construction/reports.html", report_data(request))


def number(value):
    """Число для CSV з комою як десятковим роздільником (для українського Excel)."""
    return f"{Decimal(value):.2f}".replace(".", ",")


@director_required(perm="construction.view_finance_reports")
def report_csv(request):
    data = report_data(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="budproject_report.csv"'
    response.write("\ufeff")  # щоб Excel правильно прочитав кирилицю
    writer = csv.writer(response, delimiter=";")

    writer.writerow(["Бюджет і витрати проєктів"])
    writer.writerow(["Проєкт", "Статус", "Бюджет, грн", "Витрати, грн", "Залишок, грн", "Використано, %",
                     "Витрати за період, грн", "Вартість матеріалів, грн"])
    for row in data["rows"]:
        p = row["project"]
        writer.writerow([p.name, p.get_status_display(), number(p.budget), number(row["spent"]),
                         number(p.remaining), p.budget_percent, number(row["period"]), number(p.materials_cost)])

    writer.writerow([])
    period = f'{data["date_from"] or "початок"} — {data["date_to"] or "сьогодні"}'
    writer.writerow([f"Витрати за категоріями ({period})"])
    writer.writerow(["Категорія", "Сума, грн", "Частка, %"])
    for row in data["category_rows"]:
        writer.writerow([row["label"], number(row["total"]), row["percent"]])

    writer.writerow([])
    writer.writerow([f"Витрати за місяцями ({period})"])
    writer.writerow(["Місяць", "Сума, грн"])
    for row in data["month_rows"]:
        writer.writerow([row["label"], number(row["total"])])
    return response


# ================================================================ налаштування (function-based: дві форми на одній сторінці)
@login_required
def app_settings(request):
    profile_form = ProfileForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)
    if request.method == "POST":
        if "save_profile" in request.POST:
            profile_form = ProfileForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Профіль оновлено.")
                return redirect("construction:app_settings")
        elif "change_password" in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)  # щоб користувача не розлогінило
                messages.success(request, "Пароль змінено.")
                return redirect("construction:app_settings")
    style_fields(password_form)
    counts = []
    if request.is_director:
        counts = [(label, for_user(model, request.user).count()) for label, model in (
            ("Проєкти", Project), ("Завдання", Task), ("Працівники", Worker),
            ("Матеріали", Material), ("Витрати", Expense))]
    return render(request, "construction/settings.html", {
        "profile_form": profile_form, "password_form": password_form, "counts": counts,
    })


# ================================================================ кабінет працівника
@worker_required
def my_tasks(request):
    worker = request.worker
    tasks = worker.tasks.select_related("project").annotate(
        my_hours=Sum("logs__hours", filter=Q(logs__worker=worker)))
    tasks = sorted(tasks, key=lambda t: (t.status == Task.Status.DONE, t.due_date))
    today = timezone.localdate()
    hours, pay = month_totals(worker.logs.filter(date__year=today.year, date__month=today.month))
    return render(request, "construction/my_tasks.html", {
        "worker": worker, "tasks": tasks,
        "active_count": sum(t.status != Task.Status.DONE for t in tasks),
        "in_progress_count": sum(t.status == Task.Status.IN_PROGRESS for t in tasks),
        "done_count": sum(t.status == Task.Status.DONE for t in tasks),
        "hours": hours, "pay": pay, "month": month_info(today.year, today.month),
    })


@worker_required
@require_POST
def my_task_status(request, pk, status):
    task = get_object_or_404(Task, pk=pk, assignee=request.worker)  # чужі завдання змінити не можна
    if status in (Task.Status.IN_PROGRESS, Task.Status.DONE):
        task.status = status
        task.save()
        messages.success(request, f"Завдання «{task.title}»: {task.get_status_display().lower()}.")
    return redirect("construction:my_tasks")


@worker_required
def my_hours(request):
    worker = request.worker
    initial = {"task": request.GET["task"]} if request.GET.get("task", "").isdigit() else {}
    form = WorkLogForm(request.POST or None, instance=WorkLog(worker=worker), worker=worker, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Години записано.")
        return redirect("construction:my_hours")
    year, month = get_month(request)
    logs = worker.logs.filter(date__year=year, date__month=month).select_related("task", "task__project")
    hours, pay = month_totals(logs)
    return render(request, "construction/my_hours.html", {
        "form": form, "logs": logs, "hours": hours, "pay": pay, "month": month_info(year, month),
        "has_tasks": worker.tasks.exists(),
    })


@worker_required
def my_hours_delete(request, pk):
    """Видалення свого запису годин: сторінка підтвердження (GET) і видалення (POST)."""
    log = get_object_or_404(WorkLog, pk=pk, worker=request.worker)  # лише свої записи
    back = reverse("construction:my_hours")
    if request.method == "POST":
        log.delete()
        messages.success(request, "Запис видалено.")
        return redirect(safe_next(request, back))
    return render(request, "construction/confirm_delete.html", {
        "obj": log, "title": "Видалити запис про години?", "text": "",
        "cancel_url": safe_next(request, back), "next": request.GET.get("next", "")})


@worker_required
def my_project(request):
    worker = request.worker
    project = worker.project
    return render(request, "construction/my_project.html", {
        "worker": worker, "project": project,
        "materials": project.materials.all() if project else [],
        "team": project.workers.exclude(pk=worker.pk) if project else [],
        "project_tasks": project.tasks.select_related("assignee") if project else [],
    })


@worker_required
def my_salary(request):
    worker = request.worker
    year, month = get_month(request)
    logs = worker.logs.filter(date__year=year, date__month=month)
    hours, pay = month_totals(logs)
    by_task = logs.values("task__title").annotate(total_hours=Sum("hours"), total_pay=PAY).order_by("-total_hours")

    history = []  # останні 6 місяців
    y, m = year, month
    for _ in range(6):
        h, p = month_totals(worker.logs.filter(date__year=y, date__month=m))
        history.append({**month_info(y, m), "hours": h, "pay": p})
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return render(request, "construction/my_salary.html", {
        "worker": worker, "month": month_info(year, month), "hours": hours, "pay": pay,
        "by_task": by_task, "days": logs.values("date").distinct().count(), "history": history,
        "done_total": worker.tasks.filter(status=Task.Status.DONE).count(),
    })


# ================================================================ табель (Generic Views) і зарплати (function-based)
class TimesheetListView(DirectorMixin, OwnedMixin, ListView):
    model = WorkLog
    template_name = "construction/timesheet_list.html"
    context_object_name = "logs"
    paginate_by = 15

    def get_queryset(self):
        self.year, self.month = get_month(self.request)
        logs = super().get_queryset().select_related("worker", "task", "task__project")
        logs = logs.filter(date__year=self.year, date__month=self.month)
        self.worker_id = self.request.GET.get("worker", "")
        self.project_id = self.request.GET.get("project", "")
        if self.worker_id.isdigit():
            logs = logs.filter(worker_id=self.worker_id)
        if self.project_id.isdigit():
            logs = logs.filter(task__project_id=self.project_id)
        return logs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hours, pay = month_totals(self.object_list)  # підсумок по всьому місяцю, а не по сторінці
        context.update(
            hours=hours, pay=pay, month=month_info(self.year, self.month),
            worker_id=self.worker_id, project_id=self.project_id,
            workers=for_user(Worker, self.request.user), projects=for_user(Project, self.request.user))
        return context


class TimesheetDetailView(BaseDetailView):
    model = WorkLog
    back, edit, delete = "timesheet_list", "timesheet_edit", "timesheet_delete"
    detail_fields = (
        ("Працівник", "worker"), ("Завдання", "task"), ("Дата", "date"), ("Години", "hours"),
        ("Ставка на момент запису, ₴/год", "rate"), ("Сума, ₴", "pay"), ("Що зроблено", "comment"),
    )

    def get_queryset(self):
        return super().get_queryset().select_related("worker", "task")


class TimesheetCreateView(BaseCreateView):
    model = WorkLog
    form_class = WorkLogForm
    title = "Новий запис у табель"
    back = "timesheet_list"
    initial_params = ("worker",)


class TimesheetUpdateView(BaseUpdateView):
    model = WorkLog
    form_class = WorkLogForm
    title = "Редагування запису табеля"
    back = "timesheet_list"


class TimesheetDeleteView(BaseDeleteView):
    model = WorkLog
    title = "Видалити запис табеля?"
    back = "timesheet_list"


@director_required(perm="construction.manage_payroll")
def payroll(request):
    year, month = get_month(request)
    workers = list(for_user(Worker, request.user).select_related("project"))
    sums = {r["worker"]: r for r in for_user(WorkLog, request.user)
            .filter(date__year=year, date__month=month)
            .values("worker").annotate(total_hours=Sum("hours"), total_pay=PAY).order_by()}
    # уже внесені зарплати - одним запитом, а не по запиту на кожного працівника
    titles = [salary_title(w, year, month) for w in workers]
    posted = {(e.project_id, e.title): e for e in
              for_user(Expense, request.user).filter(category=Expense.Category.SALARY, title__in=titles)}
    rows = []
    for worker in workers:
        data = sums.get(worker.id)
        rows.append({"worker": worker, "hours": data["total_hours"] if data else ZERO,
                     "pay": data["total_pay"] if data else ZERO,
                     "posted": posted.get((worker.project_id, salary_title(worker, year, month)))})
    return render(request, "construction/payroll.html", {
        "rows": rows, "month": month_info(year, month),
        "total_hours": sum((r["hours"] for r in rows), ZERO), "total_pay": sum((r["pay"] for r in rows), ZERO),
    })


@director_required(perm="construction.manage_payroll")
@require_POST
def payroll_post(request):
    """Вносить зарплату працівника за місяць у витрати проєкту (повторне натискання лише оновлює суму)."""
    parsed = parse_month(request.POST.get("month", ""))
    worker_id = request.POST.get("worker", "")
    if not parsed or not worker_id.isdigit():
        messages.error(request, "Некоректні дані.")
        return redirect("construction:payroll")
    year, month = parsed
    worker = get_object_or_404(for_user(Worker, request.user), pk=worker_id)
    _, pay = month_totals(worker.logs.filter(date__year=year, date__month=month))
    if not worker.project_id:
        messages.error(request, f"{worker.full_name} не прикріплений до проєкту: спочатку оберіть проєкт.")
    elif pay <= 0:
        messages.error(request, f"У {worker.full_name} за цей місяць немає нарахувань.")
    else:
        Expense.objects.update_or_create(
            project=worker.project, category=Expense.Category.SALARY, title=salary_title(worker, year, month),
            defaults={"amount": pay, "date": date(year, month, calendar.monthrange(year, month)[1]),
                      "description": "Нараховано за табелем відпрацьованих годин."})
        messages.success(request, f"Зарплату {worker.full_name} ({pay} ₴) внесено у витрати проєкту «{worker.project.name}».")
    return redirect(f"{reverse('construction:payroll')}?month={year}-{month:02d}")
