from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .access import WORKER_GROUP, sync_roles
from .forms import RegisterForm, TaskForm, WorkLogForm, WorkerForm
from .models import Expense, Material, Project, Task, WorkLog, Worker
from .validators import validate_phone, validate_quarter_hour
from django.core.exceptions import ValidationError


def url(name, *args):
    return reverse(f"construction:{name}", args=args)


class BaseCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.director_group = sync_roles()
        cls.boss = User.objects.create_user("boss", password="pw12345678")
        cls.boss.groups.add(cls.director_group)
        cls.other = User.objects.create_user("other", password="pw12345678")
        cls.other.groups.add(cls.director_group)
        cls.admin = User.objects.create_superuser("root", password="pw12345678")
        cls.project = Project.objects.create(
            name="Дім", address="Львів", budget=1000, start_date=date.today() - timedelta(days=5),
            end_date=date.today() + timedelta(days=50), status="active", owner=cls.boss)
        cls.theirs = Project.objects.create(
            name="Чужий", address="Київ", budget=500, start_date=date.today(),
            end_date=date.today() + timedelta(days=30), status="active", owner=cls.other)
        worker_user = User.objects.create_user("wk", password="pw12345678")
        cls.worker = Worker.objects.create(first_name="Іван", last_name="Скляр", position="builder",
                                           phone="+380501112233", project=cls.project, hourly_rate=100,
                                           user=worker_user, owner=cls.boss)
        cls.task = Task.objects.create(project=cls.project, title="Фундамент", assignee=cls.worker,
                                       due_date=date.today() + timedelta(days=5))
        cls.material = Material.objects.create(project=cls.project, name="Цемент", quantity=10, unit="pcs", unit_price=5)
        cls.expense = Expense.objects.create(project=cls.project, title="Бетон", category="materials",
                                             amount=100, date=date.today())
        cls.log = WorkLog.objects.create(worker=cls.worker, task=cls.task, date=date.today(), hours=Decimal("8"))

    def login(self, user):
        self.client.force_login(user)


class AccessTests(BaseCase):
    def test_anonymous_redirected_to_login(self):
        response = self.client.get(url("project_list"))
        self.assertRedirects(response, f"{url('login')}?next={url('project_list')}")

    def test_director_pages_open(self):
        self.login(self.boss)
        names = [("dashboard",), ("project_list",), ("project_create",), ("project_detail", self.project.pk),
                 ("project_edit", self.project.pk), ("project_delete", self.project.pk),
                 ("task_list",), ("task_create",), ("task_detail", self.task.pk), ("task_edit", self.task.pk),
                 ("task_delete", self.task.pk), ("worker_list",), ("worker_create",),
                 ("worker_detail", self.worker.pk), ("worker_edit", self.worker.pk), ("worker_delete", self.worker.pk),
                 ("material_list",), ("material_create",), ("material_detail", self.material.pk),
                 ("material_edit", self.material.pk), ("material_delete", self.material.pk),
                 ("material_catalog",), ("material_catalog_create",), ("expense_list",), ("expense_create",),
                 ("expense_detail", self.expense.pk), ("expense_edit", self.expense.pk),
                 ("expense_delete", self.expense.pk), ("timesheet_list",), ("timesheet_create",),
                 ("timesheet_detail", self.log.pk), ("timesheet_edit", self.log.pk),
                 ("timesheet_delete", self.log.pk), ("payroll",), ("report_list",), ("report_csv",),
                 ("app_settings",)]
        for name, *args in names:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(url(name, *args)).status_code, 200)

    def test_worker_cannot_open_director_pages(self):
        self.login(self.worker.user)
        for name in ("project_list", "task_list", "payroll", "report_list", "expense_list"):
            with self.subTest(name=name):
                self.assertRedirects(self.client.get(url(name)), url("my_tasks"), fetch_redirect_response=False)
        for name in ("my_tasks", "my_hours", "my_project", "my_salary", "app_settings"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(url(name)).status_code, 200)

    def test_director_cannot_open_worker_cabinet(self):
        self.login(self.boss)
        self.assertRedirects(self.client.get(url("my_tasks")), url("dashboard"), fetch_redirect_response=False)

    def test_foreign_records_are_404(self):
        self.login(self.other)
        for name in ("project_detail", "project_edit", "project_delete"):
            self.assertEqual(self.client.get(url(name, self.project.pk)).status_code, 404)
        for name in ("task_edit", "task_detail", "task_delete"):
            self.assertEqual(self.client.get(url(name, self.task.pk)).status_code, 404)
        self.assertEqual(self.client.post(url("project_delete", self.project.pk)).status_code, 404)
        self.assertEqual(self.client.post(url("task_done", self.task.pk)).status_code, 404)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())

    def test_foreign_records_not_listed(self):
        self.login(self.other)
        self.assertNotContains(self.client.get(url("project_list")), "Дім")
        self.assertContains(self.client.get(url("project_list")), "Чужий")

    def test_superuser_sees_everything(self):
        self.login(self.admin)
        page = self.client.get(url("project_list"))
        self.assertContains(page, "Дім")
        self.assertContains(page, "Чужий")

    def test_logout_requires_post(self):
        self.login(self.boss)
        self.assertEqual(self.client.get(url("logout")).status_code, 405)
        self.client.post(url("logout"))
        self.assertEqual(self.client.get(url("project_list")).status_code, 302)

    def test_delete_only_by_post(self):
        self.login(self.boss)
        self.client.get(url("project_delete", self.project.pk))
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        response = self.client.post(url("project_delete", self.project.pk))
        self.assertRedirects(response, url("project_list"))
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())

    def test_director_without_permission_blocked(self):
        limited = User.objects.create_user("limited", password="pw12345678")
        from django.contrib.auth.models import Group
        limited.groups.add(Group.objects.create(name="Директор-обмежений"))
        # не директор (немає групи «Директор») -> у кабінет працівника, а не на звіти
        self.login(limited)
        self.assertEqual(self.client.get(url("report_list")).status_code, 302)

    def test_director_without_right_cannot_see_payroll(self):
        self.director_group.permissions.remove(*self.director_group.permissions.filter(codename="manage_payroll"))
        user = User.objects.get(pk=self.boss.pk)
        self.login(user)
        self.assertRedirects(self.client.get(url("payroll")), url("dashboard"), fetch_redirect_response=False)


class OwnerTests(BaseCase):
    def test_owner_assigned_in_form_valid(self):
        self.login(self.boss)
        data = {"name": "Новий", "address": "Адреса", "description": "", "budget": "100",
                "start_date": "2026-01-01", "end_date": "2026-02-01", "status": "planned"}
        response = self.client.post(url("project_create"), data)
        project = Project.objects.get(name="Новий")
        self.assertEqual(project.owner, self.boss)
        self.assertRedirects(response, project.get_absolute_url())

    def test_owner_cannot_be_forged_via_post(self):
        self.login(self.boss)
        data = {"name": "Підробка", "address": "А", "budget": "100", "start_date": "2026-01-01",
                "end_date": "2026-02-01", "status": "planned", "owner": self.other.pk}
        self.client.post(url("project_create"), data)
        self.assertEqual(Project.objects.get(name="Підробка").owner, self.boss)

    def test_duplicate_project_name_rejected(self):
        self.login(self.boss)
        data = {"name": "дім", "address": "А", "budget": "100", "start_date": "2026-01-01",
                "end_date": "2026-02-01", "status": "planned"}
        response = self.client.post(url("project_create"), data)
        self.assertContains(response, "У вас уже є проєкт з такою назвою.")

    def test_cannot_use_foreign_project_in_form(self):
        self.login(self.boss)
        data = {"project": self.theirs.pk, "title": "Хакерське", "due_date": "2026-12-01", "status": "pending"}
        response = self.client.post(url("task_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Task.objects.filter(title="Хакерське").exists())

    def test_worker_creation_gets_group_and_owner(self):
        self.login(self.boss)
        data = {"first_name": "Нова", "last_name": "Людина", "position": "builder", "phone": "+380671234567",
                "hourly_rate": "120", "project": self.project.pk, "username": "newbie", "password": "Str0ng-pass-77"}
        self.client.post(url("worker_create"), data)
        worker = Worker.objects.get(last_name="Людина")
        self.assertEqual(worker.owner, self.boss)
        self.assertTrue(worker.user.groups.filter(name=WORKER_GROUP).exists())


class RegistrationTests(TestCase):
    def test_register_creates_director_and_logs_in(self):
        sync_roles()
        response = self.client.post(url("register"), {
            "username": "newdirector", "first_name": "Ольга", "last_name": "Мазур", "email": "olga@example.com",
            "password1": "Str0ng-pass-77", "password2": "Str0ng-pass-77"})
        self.assertRedirects(response, url("dashboard"))
        user = User.objects.get(username="newdirector")
        self.assertTrue(user.groups.filter(name="Директор").exists())
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(self.client.get(url("dashboard")).status_code, 200)

    def test_register_errors_in_ukrainian(self):
        form = RegisterForm({"username": "x", "password1": "1", "password2": "2"})
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
        self.assertEqual(form.errors["email"][0], "Вкажіть електронну пошту.")


class ValidationTests(BaseCase):
    def test_phone_validator(self):
        validate_phone("+380501112233")
        with self.assertRaisesMessage(ValidationError, "Введіть коректний номер телефону"):
            validate_phone("abc")

    def test_quarter_hour_validator(self):
        validate_quarter_hour(Decimal("7.5"))
        with self.assertRaises(ValidationError):
            validate_quarter_hour(Decimal("7.3"))

    def test_task_materials_must_belong_to_project(self):
        other_material = Material.objects.create(project=self.theirs, name="Чужий цемент", quantity=1, unit="pcs", unit_price=1)
        other_project = Project.objects.create(name="Другий", address="А", budget=1, start_date=date.today(),
                                               end_date=date.today() + timedelta(days=3), owner=self.boss)
        form = TaskForm({"project": other_project.pk, "title": "Завдання", "due_date": "2026-12-01",
                         "status": "pending", "materials": [self.material.pk]}, user=self.boss)
        self.assertFalse(form.is_valid())
        self.assertIn("materials", form.errors)
        self.assertNotIn(other_material, form.fields["materials"].queryset)

    def test_expense_amount_positive(self):
        self.login(self.boss)
        data = {"project": self.project.pk, "title": "Нуль", "category": "other", "amount": "0", "date": "2026-01-01"}
        self.assertContains(self.client.post(url("expense_create"), data), "Сума витрати має бути більшою за нуль.")

    def test_worklog_hours_step_in_form(self):
        form = WorkLogForm({"task": self.task.pk, "date": date.today(), "hours": "7.3", "comment": ""},
                           instance=WorkLog(worker=self.worker), worker=self.worker)
        self.assertFalse(form.is_valid())
        self.assertIn("hours", form.errors)

    def test_no_next_open_redirect(self):
        self.login(self.boss)
        response = self.client.post(url("task_done", self.task.pk), {"next": "https://evil.example/"})
        self.assertRedirects(response, url("task_list"), fetch_redirect_response=False)


class PaginationAndQueryTests(BaseCase):
    def test_project_list_paginated(self):
        for i in range(12):
            Project.objects.create(name=f"П{i}", address="а", budget=10, start_date=date.today(),
                                   end_date=date.today() + timedelta(days=2), owner=self.boss)
        self.login(self.boss)
        page = self.client.get(url("project_list"))
        self.assertEqual(len(page.context["projects"]), 8)
        self.assertEqual(len(self.client.get(url("project_list") + "?page=2").context["projects"]), 5)

    def test_project_list_has_no_n_plus_one(self):
        self.login(self.boss)
        with CaptureQueriesContext(connection) as few:
            self.client.get(url("project_list"))
        for i in range(10):
            p = Project.objects.create(name=f"Q{i}", address="а", budget=10, start_date=date.today(),
                                       end_date=date.today() + timedelta(days=2), owner=self.boss)
            Expense.objects.create(project=p, title="e", category="other", amount=1, date=date.today())
            Task.objects.create(project=p, title="task", due_date=date.today())
        with CaptureQueriesContext(connection) as many:
            self.client.get(url("project_list") + "?page=1")
        self.assertEqual(len(few), len(many))

    def test_totals_annotation(self):
        project = Project.objects.with_totals().get(pk=self.project.pk)
        self.assertEqual(project.spent, Decimal("100"))
        self.assertEqual(project.materials_cost, Decimal("50"))
        self.assertEqual(project.progress, 0)
        Task.objects.filter(pk=self.task.pk).update(status="done")
        self.assertEqual(Project.objects.with_totals().get(pk=self.project.pk).progress, 100)

    def test_search_q_objects(self):
        self.login(self.boss)
        page = self.client.get(url("project_list") + "?q=Львів")
        self.assertEqual(len(page.context["projects"]), 1)


class PayrollTests(BaseCase):
    def test_payroll_post_creates_expense_once(self):
        self.login(self.boss)
        month = date.today().strftime("%Y-%m")
        for _ in range(2):
            self.client.post(url("payroll_post"), {"worker": self.worker.pk, "month": month})
        self.assertEqual(Expense.objects.filter(category="salary").count(), 1)
        self.assertEqual(Expense.objects.get(category="salary").amount, Decimal("800"))

    def test_password_reset_page(self):
        self.assertEqual(self.client.get(url("password_reset")).status_code, 200)
