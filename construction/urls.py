from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "construction"

urlpatterns = [
    # ---- вхід, вихід (лише POST), реєстрація, скидання пароля
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("password-reset/", auth_views.PasswordResetView.as_view(
        template_name="registration/password_reset_form.html",
        email_template_name="registration/password_reset_email.txt",
        subject_template_name="registration/password_reset_subject.txt",
        success_url=reverse_lazy("construction:password_reset_done")), name="password_reset"),
    path("password-reset/sent/", auth_views.PasswordResetDoneView.as_view(
        template_name="registration/password_reset_done.html"), name="password_reset_done"),
    path("password-reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="registration/password_reset_confirm.html",
        success_url=reverse_lazy("construction:password_reset_complete")), name="password_reset_confirm"),
    path("password-reset/complete/", auth_views.PasswordResetCompleteView.as_view(
        template_name="registration/password_reset_complete.html"), name="password_reset_complete"),

    path("", views.dashboard, name="dashboard"),

    # ---- проєкти
    path("projects/", views.ProjectListView.as_view(), name="project_list"),
    path("projects/new/", views.ProjectCreateView.as_view(), name="project_create"),
    path("projects/<int:pk>/", views.ProjectDetailView.as_view(), name="project_detail"),
    path("projects/<int:pk>/edit/", views.ProjectUpdateView.as_view(), name="project_edit"),
    path("projects/<int:pk>/delete/", views.ProjectDeleteView.as_view(), name="project_delete"),

    # ---- завдання
    path("tasks/", views.TaskListView.as_view(), name="task_list"),
    path("tasks/new/", views.TaskCreateView.as_view(), name="task_create"),
    path("tasks/<int:pk>/", views.TaskDetailView.as_view(), name="task_detail"),
    path("tasks/<int:pk>/edit/", views.TaskUpdateView.as_view(), name="task_edit"),
    path("tasks/<int:pk>/delete/", views.TaskDeleteView.as_view(), name="task_delete"),
    path("tasks/<int:pk>/done/", views.task_done, name="task_done"),

    # ---- працівники
    path("workers/", views.WorkerListView.as_view(), name="worker_list"),
    path("workers/new/", views.WorkerCreateView.as_view(), name="worker_create"),
    path("workers/<int:pk>/", views.WorkerDetailView.as_view(), name="worker_detail"),
    path("workers/<int:pk>/edit/", views.WorkerUpdateView.as_view(), name="worker_edit"),
    path("workers/<int:pk>/delete/", views.WorkerDeleteView.as_view(), name="worker_delete"),

    # ---- матеріали та каталог
    path("materials/", views.MaterialListView.as_view(), name="material_list"),
    path("materials/new/", views.MaterialCreateView.as_view(), name="material_create"),
    path("materials/catalog/", views.CatalogListView.as_view(), name="material_catalog"),
    path("materials/catalog/new/", views.CatalogCreateView.as_view(), name="material_catalog_create"),
    path("materials/catalog/<int:pk>/", views.CatalogDetailView.as_view(), name="catalog_detail"),
    path("materials/catalog/<int:pk>/edit/", views.CatalogUpdateView.as_view(), name="catalog_edit"),
    path("materials/catalog/<int:pk>/delete/", views.CatalogDeleteView.as_view(), name="catalog_delete"),
    path("materials/<int:pk>/", views.MaterialDetailView.as_view(), name="material_detail"),
    path("materials/<int:pk>/edit/", views.MaterialUpdateView.as_view(), name="material_edit"),
    path("materials/<int:pk>/delete/", views.MaterialDeleteView.as_view(), name="material_delete"),

    # ---- витрати
    path("expenses/", views.ExpenseListView.as_view(), name="expense_list"),
    path("expenses/new/", views.ExpenseCreateView.as_view(), name="expense_create"),
    path("expenses/<int:pk>/", views.ExpenseDetailView.as_view(), name="expense_detail"),
    path("expenses/<int:pk>/edit/", views.ExpenseUpdateView.as_view(), name="expense_edit"),
    path("expenses/<int:pk>/delete/", views.ExpenseDeleteView.as_view(), name="expense_delete"),

    # ---- звіти
    path("reports/", views.report_list, name="report_list"),
    path("reports/export/", views.report_csv, name="report_csv"),

    # ---- табель і зарплати
    path("timesheet/", views.TimesheetListView.as_view(), name="timesheet_list"),
    path("timesheet/new/", views.TimesheetCreateView.as_view(), name="timesheet_create"),
    path("timesheet/<int:pk>/", views.TimesheetDetailView.as_view(), name="timesheet_detail"),
    path("timesheet/<int:pk>/edit/", views.TimesheetUpdateView.as_view(), name="timesheet_edit"),
    path("timesheet/<int:pk>/delete/", views.TimesheetDeleteView.as_view(), name="timesheet_delete"),
    path("payroll/", views.payroll, name="payroll"),
    path("payroll/post/", views.payroll_post, name="payroll_post"),

    # ---- кабінет працівника
    path("my/", views.my_tasks, name="my_tasks"),
    path("my/tasks/<int:pk>/<str:status>/", views.my_task_status, name="my_task_status"),
    path("my/hours/", views.my_hours, name="my_hours"),
    path("my/hours/<int:pk>/delete/", views.my_hours_delete, name="my_hours_delete"),
    path("my/project/", views.my_project, name="my_project"),
    path("my/salary/", views.my_salary, name="my_salary"),

    path("settings/", views.app_settings, name="app_settings"),
]
