import calendar
import csv
from datetime import date
from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import DecimalField, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (CatalogItemForm, ExpenseForm, MaterialForm, ProfileForm, ProjectForm,
                    TaskForm, WorkLogForm, WorkerForm, style_fields)
from .models import ZERO, CatalogItem, Expense, Material, Project, Task, WorkLog, Worker

MONTHS = ["січ", "лют", "бер", "кві", "тра", "чер", "лип", "сер", "вер", "жов", "лис", "гру"]
MATERIAL_COST = Sum(F("quantity") * F("unit_price"), output_field=DecimalField(max_digits=18, decimal_places=2))
PAY = Sum(F("hours") * F("rate"), output_field=DecimalField(max_digits=14, decimal_places=2))
MONTH_NAMES = ["січень", "лютий", "березень", "квітень", "травень", "червень",
               "липень", "серпень", "вересень", "жовтень", "листопад", "грудень"]


# ---------------------------------------------------------------- ролі
# Директор - користувач з is_staff (звичайний admin). Працівник - користувач, прив'язаний до запису Worker.
def director_required(view):
    """Сторінка лише для директора. Працівника переспрямовує в його кабінет."""
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            messages.error(request, "Ця сторінка доступна лише директору.")
            return redirect("my_tasks")
        return view(request, *args, **kwargs)
    return wrapper


def worker_required(view):
    """Сторінка кабінету працівника. У request.worker лежить його запис."""
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        worker = Worker.objects.select_related("project").filter(user=request.user).first()
        if worker is None:
            if request.user.is_staff:
                return redirect("dashboard")
            return render(request, "construction/no_profile.html")
        request.worker = worker
        return view(request, *args, **kwargs)
    return wrapper


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


# ---------------------------------------------------------------- допоміжні функції
def total(queryset, field="amount"):
    """Сума поля по queryset (0, якщо записів немає)."""
    return queryset.aggregate(t=Sum(field))["t"] or ZERO


def get_date(request, name):
    """Дата з GET-параметра або None, якщо її немає чи вона некоректна."""
    try:
        return parse_date(request.GET.get(name) or "")
    except ValueError:
        return None


def by_category(expenses):
    """Витрати, згруповані за категоріями, з відсотками від загальної суми."""
    labels = dict(Expense.Category.choices)
    rows = expenses.values("category").annotate(total=Sum("amount")).order_by("-total")
    all_total = sum((r["total"] for r in rows), ZERO)
    return [
        {"key": r["category"], "label": labels[r["category"]], "total": r["total"],
         "percent": int(round(r["total"] * 100 / all_total)) if all_total else 0}
        for r in rows
    ]


def by_month(expenses):
    """Витрати за місяцями: словник {(рік, місяць): сума}."""
    rows = expenses.annotate(month=TruncMonth("date")).values("month").annotate(total=Sum("amount")).order_by("month")
    return {(r["month"].year, r["month"].month): r["total"] for r in rows}


def month_rows(expenses):
    sums = by_month(expenses)
    return [{"label": f"{MONTHS[m - 1]} {y}", "total": t} for (y, m), t in sorted(sums.items())]


def project_initial(request):
    """Підставляє проєкт у форму, якщо в адресі є ?project=ID."""
    project_id = request.GET.get("project", "")
    return {"project": project_id} if project_id.isdigit() else {}


def safe_next(request, default_url):
    """Адреса повернення з параметра next (лише всередині сайту)."""
    url = request.POST.get("next") or request.GET.get("next") or ""
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}):
        return url
    return default_url


def form_page(request, form_class, title, back, instance=None, initial=None):
    """Спільна логіка створення та редагування. back — ім'я маршруту списку."""
    form = form_class(request.POST or None, instance=instance, initial=initial)
    cancel_url = safe_next(request, reverse(back))
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, "Зміни збережено." if instance else "Запис створено.")
        if cancel_url != reverse(back):
            return redirect(cancel_url)
        # проєкт має власну сторінку, решта записів повертає до свого списку
        return redirect(obj) if hasattr(obj, "get_absolute_url") else redirect(back)
    return render(request, "construction/form.html",
                  {"form": form, "title": title, "cancel_url": cancel_url, "next": request.GET.get("next", "")})


def confirm_delete(request, obj, title, back, text=""):
    """Сторінка підтвердження; видалення виконується лише POST-запитом."""
    if request.method == "POST":
        name = str(obj)
        obj.delete()
        messages.success(request, f"«{name}» видалено.")
        return redirect(safe_next(request, reverse(back)))
    return render(request, "construction/confirm_delete.html",
                  {"obj": obj, "title": title, "text": text,
                   "cancel_url": safe_next(request, reverse(back)), "next": request.GET.get("next", "")})


# ---------------------------------------------------------------- головна
@login_required
def dashboard(request):
    if not request.user.is_staff:
        return redirect("my_tasks")
    projects = list(Project.objects.all())
    expenses = Expense.objects.all()
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

    unfinished = Task.objects.exclude(status=Task.Status.DONE)
    context = {
        "projects_count": len(projects),
        "active_count": sum(p.status == Project.Status.ACTIVE for p in projects),
        "completed_count": sum(p.status == Project.Status.COMPLETED for p in projects),
        "total_budget": total_budget,
        "total_spent": total_spent,
        "total_remaining": total_budget - total_spent,
        "workers_count": Worker.objects.count(),
        "unfinished_count": unfinished.count(),
        "recent_projects": projects[:5],
        "chart": chart,
        "chart_has_data": biggest > 0,
        "categories": by_category(expenses),
        "alerts": [p for p in projects if p.status != Project.Status.COMPLETED and p.budget_percent >= 90],
        "upcoming": unfinished.select_related("project").order_by("due_date")[:6],
    }
    return render(request, "construction/dashboard.html", context)


# ---------------------------------------------------------------- проєкти
SORTS = {
    "new": ("-start_date", "Дата початку: спочатку нові"),
    "old": ("start_date", "Дата початку: спочатку старі"),
    "budget_desc": ("-budget", "Бюджет: від більшого"),
    "budget_asc": ("budget", "Бюджет: від меншого"),
}


@director_required
def project_list(request):
    projects = Project.objects.all()
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    sort = request.GET.get("sort", "new")
    if q:
        projects = projects.filter(name__icontains=q)
    if status:
        projects = projects.filter(status=status)
    projects = projects.order_by(SORTS.get(sort, SORTS["new"])[0])
    return render(request, "construction/project_list.html", {
        "projects": projects, "q": q, "status": status, "sort": sort,
        "statuses": Project.Status.choices, "sorts": [(k, v[1]) for k, v in SORTS.items()],
    })


@director_required
def project_detail(request, pk):
    project = get_object_or_404(Project, pk=pk)
    return render(request, "construction/project_detail.html", {
        "project": project,
        "tasks": project.tasks.all(),
        "workers": project.workers.all(),
        "materials": project.materials.all(),
        "expenses": project.expenses.all(),
    })


@director_required
def project_create(request):
    return form_page(request, ProjectForm, "Новий проєкт", back="project_list")


@director_required
def project_edit(request, pk):
    project = get_object_or_404(Project, pk=pk)
    return form_page(request, ProjectForm, "Редагування проєкту", back="project_list", instance=project)


@director_required
def project_delete(request, pk):
    project = get_object_or_404(Project, pk=pk)
    text = ("Разом із проєктом буде видалено всі його завдання, матеріали та витрати. "
            "Працівники залишаться в системі, але стануть відкріпленими від проєкту.")
    return confirm_delete(request, project, "Видалити проєкт?", "project_list", text)


# ---------------------------------------------------------------- завдання
@director_required
def task_list(request):
    tasks = Task.objects.select_related("project", "assignee")
    q = request.GET.get("q", "").strip()
    project_id = request.GET.get("project", "")
    status = request.GET.get("status", "")
    assignee_id = request.GET.get("assignee", "")
    if q:
        tasks = tasks.filter(title__icontains=q)
    if project_id.isdigit():
        tasks = tasks.filter(project_id=project_id)
    if status:
        tasks = tasks.filter(status=status)
    if assignee_id.isdigit():
        tasks = tasks.filter(assignee_id=assignee_id)
    return render(request, "construction/task_list.html", {
        "tasks": tasks, "q": q, "project_id": project_id, "status": status, "assignee_id": assignee_id,
        "projects": Project.objects.all(), "statuses": Task.Status.choices, "workers": Worker.objects.all(),
    })


@director_required
def task_create(request):
    return form_page(request, TaskForm, "Нове завдання", back="task_list", initial=project_initial(request))


@director_required
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk)
    return form_page(request, TaskForm, "Редагування завдання", back="task_list", instance=task)


@director_required
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    return confirm_delete(request, task, "Видалити завдання?", "task_list")


@director_required
@require_POST
def task_done(request, pk):
    task = get_object_or_404(Task, pk=pk)
    task.status = Task.Status.DONE
    task.save()
    messages.success(request, f"Завдання «{task.title}» позначено виконаним.")
    return redirect(safe_next(request, reverse("task_list")))


# ---------------------------------------------------------------- працівники
@director_required
def worker_list(request):
    workers = Worker.objects.select_related("project")
    q = request.GET.get("q", "").strip()
    position = request.GET.get("position", "")
    project_id = request.GET.get("project", "")
    if q:
        workers = workers.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q))
    if position:
        workers = workers.filter(position=position)
    if project_id.isdigit():
        workers = workers.filter(project_id=project_id)
    return render(request, "construction/worker_list.html", {
        "workers": workers, "q": q, "position": position, "project_id": project_id,
        "positions": Worker.Position.choices, "projects": Project.objects.all(),
    })


@director_required
def worker_create(request):
    return form_page(request, WorkerForm, "Новий працівник", back="worker_list", initial=project_initial(request))


@director_required
def worker_edit(request, pk):
    worker = get_object_or_404(Worker, pk=pk)
    return form_page(request, WorkerForm, "Редагування працівника", back="worker_list", instance=worker)


@director_required
def worker_delete(request, pk):
    worker = get_object_or_404(Worker, pk=pk)
    return confirm_delete(request, worker, "Видалити працівника?", "worker_list")


# ---------------------------------------------------------------- матеріали
@director_required
def material_list(request):
    materials = Material.objects.select_related("project")
    q = request.GET.get("q", "").strip()
    project_id = request.GET.get("project", "")
    if q:
        materials = materials.filter(name__icontains=q)
    if project_id.isdigit():
        materials = materials.filter(project_id=project_id)
    per_project = (Material.objects.values("project_id", "project__name")
                   .annotate(total=MATERIAL_COST).order_by("project__name"))
    return render(request, "construction/material_list.html", {
        "materials": materials, "q": q, "project_id": project_id,
        "projects": Project.objects.all(), "per_project": per_project,
        "total_cost": sum((m.cost for m in materials), ZERO),
    })


@director_required
def material_create(request):
    return form_page(request, MaterialForm, "Новий матеріал", back="material_list", initial=project_initial(request))


@director_required
def material_edit(request, pk):
    material = get_object_or_404(Material, pk=pk)
    return form_page(request, MaterialForm, "Редагування матеріалу", back="material_list", instance=material)


@director_required
def material_delete(request, pk):
    material = get_object_or_404(Material, pk=pk)
    return confirm_delete(request, material, "Видалити матеріал?", "material_list")


@director_required
def material_catalog(request):
    q = request.GET.get("q", "").strip()
    items = CatalogItem.objects.all()
    if q:
        items = items.filter(name__icontains=q)
    return render(request, "construction/material_catalog.html", {"items": items, "q": q})


@director_required
def material_catalog_create(request):
    return form_page(request, CatalogItemForm, "Нова позиція каталогу", back="material_catalog")


@director_required
def material_catalog_edit(request, pk):
    item = get_object_or_404(CatalogItem, pk=pk)
    return form_page(request, CatalogItemForm, "Редагування позиції каталогу", back="material_catalog", instance=item)


@director_required
def material_catalog_delete(request, pk):
    item = get_object_or_404(CatalogItem, pk=pk)
    text = "Матеріали, які вже додані до проєктів, не зміняться."
    return confirm_delete(request, item, "Видалити позицію каталогу?", "material_catalog", text)


# ---------------------------------------------------------------- витрати
@director_required
def expense_list(request):
    expenses = Expense.objects.select_related("project")
    q = request.GET.get("q", "").strip()
    project_id = request.GET.get("project", "")
    category = request.GET.get("category", "")
    date_from = get_date(request, "date_from")
    date_to = get_date(request, "date_to")
    if q:
        expenses = expenses.filter(title__icontains=q)
    if project_id.isdigit():
        expenses = expenses.filter(project_id=project_id)
    if category:
        expenses = expenses.filter(category=category)
    if date_from:
        expenses = expenses.filter(date__gte=date_from)
    if date_to:
        expenses = expenses.filter(date__lte=date_to)
    return render(request, "construction/expense_list.html", {
        "expenses": expenses, "q": q, "project_id": project_id, "category": category,
        "date_from": date_from, "date_to": date_to,
        "projects": Project.objects.all(), "categories": Expense.Category.choices,
        "total": total(expenses), "category_rows": by_category(expenses), "month_rows": month_rows(expenses),
    })


@director_required
def expense_create(request):
    return form_page(request, ExpenseForm, "Нова витрата", back="expense_list", initial=project_initial(request))


@director_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    return form_page(request, ExpenseForm, "Редагування витрати", back="expense_list", instance=expense)


@director_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    return confirm_delete(request, expense, "Видалити витрату?", "expense_list")


# ---------------------------------------------------------------- звіти
def report_data(request):
    """Дані для сторінки звітів і для CSV (витрати фільтруються за періодом)."""
    date_from = get_date(request, "date_from")
    date_to = get_date(request, "date_to")
    period = Expense.objects.all()
    if date_from:
        period = period.filter(date__gte=date_from)
    if date_to:
        period = period.filter(date__lte=date_to)

    period_sums = {r["project"]: r["total"]
                   for r in period.values("project").annotate(total=Sum("amount")).order_by()}
    rows = []
    for project in Project.objects.order_by("name"):
        rows.append({"project": project, "spent": project.spent, "period": period_sums.get(project.id, ZERO)})
    for row in rows:
        # масштаб смуг окремий для кожного проєкту: видно співвідношення бюджету та витрат
        scale = max(row["project"].budget, row["spent"])
        row["budget_width"] = int(row["project"].budget * 100 / scale) if scale else 0
        row["spent_width"] = int(row["spent"] * 100 / scale) if scale else 0

    return {
        "date_from": date_from, "date_to": date_to,
        "rows": rows,
        "top": sorted(rows, key=lambda r: r["spent"], reverse=True)[:5],
        "period_total": total(period),
        "period_count": period.count(),
        "category_rows": by_category(period),
        "month_rows": month_rows(period),
        "total_budget": sum((r["project"].budget for r in rows), ZERO),
        "total_spent": sum((r["spent"] for r in rows), ZERO),
    }


@director_required
def report_list(request):
    return render(request, "construction/reports.html", report_data(request))


def number(value):
    """Число для CSV з комою як десятковим роздільником (для українського Excel)."""
    return f"{Decimal(value):.2f}".replace(".", ",")


@director_required
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


# ---------------------------------------------------------------- налаштування
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
                return redirect("app_settings")
        elif "change_password" in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)  # щоб користувача не розлогінило
                messages.success(request, "Пароль змінено.")
                return redirect("app_settings")
    style_fields(password_form)
    return render(request, "construction/settings.html", {
        "profile_form": profile_form, "password_form": password_form,
        "counts": [("Проєкти", Project.objects.count()), ("Завдання", Task.objects.count()),
                   ("Працівники", Worker.objects.count()), ("Матеріали", Material.objects.count()),
                   ("Витрати", Expense.objects.count())],
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
    return redirect("my_tasks")


@worker_required
def my_hours(request):
    worker = request.worker
    initial = {"task": request.GET["task"]} if request.GET.get("task", "").isdigit() else {}
    form = WorkLogForm(request.POST or None, instance=WorkLog(worker=worker), worker=worker, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Години записано.")
        return redirect("my_hours")
    year, month = get_month(request)
    logs = worker.logs.filter(date__year=year, date__month=month).select_related("task", "task__project")
    hours, pay = month_totals(logs)
    return render(request, "construction/my_hours.html", {
        "form": form, "logs": logs, "hours": hours, "pay": pay, "month": month_info(year, month),
        "has_tasks": worker.tasks.exists(),
    })


@worker_required
def my_hours_delete(request, pk):
    log = get_object_or_404(WorkLog, pk=pk, worker=request.worker)  # лише свої записи
    return confirm_delete(request, log, "Видалити запис про години?", "my_hours")


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


# ================================================================ табель і зарплати (директор)
@director_required
def timesheet_list(request):
    year, month = get_month(request)
    logs = WorkLog.objects.select_related("worker", "task", "task__project")
    logs = logs.filter(date__year=year, date__month=month)
    worker_id = request.GET.get("worker", "")
    project_id = request.GET.get("project", "")
    if worker_id.isdigit():
        logs = logs.filter(worker_id=worker_id)
    if project_id.isdigit():
        logs = logs.filter(task__project_id=project_id)
    hours, pay = month_totals(logs)
    return render(request, "construction/timesheet_list.html", {
        "logs": logs, "hours": hours, "pay": pay, "month": month_info(year, month),
        "worker_id": worker_id, "project_id": project_id,
        "workers": Worker.objects.all(), "projects": Project.objects.all(),
    })


@director_required
def timesheet_create(request):
    initial = {"worker": request.GET["worker"]} if request.GET.get("worker", "").isdigit() else {}
    return form_page(request, WorkLogForm, "Новий запис у табель", back="timesheet_list", initial=initial)


@director_required
def timesheet_edit(request, pk):
    log = get_object_or_404(WorkLog, pk=pk)
    return form_page(request, WorkLogForm, "Редагування запису табеля", back="timesheet_list", instance=log)


@director_required
def timesheet_delete(request, pk):
    log = get_object_or_404(WorkLog, pk=pk)
    return confirm_delete(request, log, "Видалити запис табеля?", "timesheet_list")


@director_required
def payroll(request):
    year, month = get_month(request)
    sums = {r["worker"]: r for r in WorkLog.objects.filter(date__year=year, date__month=month)
            .values("worker").annotate(total_hours=Sum("hours"), total_pay=PAY).order_by()}
    rows = []
    for worker in Worker.objects.select_related("project"):
        data = sums.get(worker.id)
        posted = None
        if worker.project_id:
            posted = Expense.objects.filter(project_id=worker.project_id, category=Expense.Category.SALARY,
                                            title=salary_title(worker, year, month)).first()
        rows.append({"worker": worker, "hours": data["total_hours"] if data else ZERO,
                     "pay": data["total_pay"] if data else ZERO, "posted": posted})
    return render(request, "construction/payroll.html", {
        "rows": rows, "month": month_info(year, month),
        "total_hours": sum((r["hours"] for r in rows), ZERO), "total_pay": sum((r["pay"] for r in rows), ZERO),
    })


@director_required
@require_POST
def payroll_post(request):
    """Вносить зарплату працівника за місяць у витрати проєкту (повторне натискання лише оновлює суму)."""
    parsed = parse_month(request.POST.get("month", ""))
    worker_id = request.POST.get("worker", "")
    if not parsed or not worker_id.isdigit():
        messages.error(request, "Некоректні дані.")
        return redirect("payroll")
    year, month = parsed
    worker = get_object_or_404(Worker, pk=worker_id)
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
    return redirect(f"{reverse('payroll')}?month={year}-{month:02d}")
