from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    path("", views.dashboard, name="dashboard"),

    path("projects/", views.project_list, name="project_list"),
    path("projects/new/", views.project_create, name="project_create"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("projects/<int:pk>/edit/", views.project_edit, name="project_edit"),
    path("projects/<int:pk>/delete/", views.project_delete, name="project_delete"),

    path("tasks/", views.task_list, name="task_list"),
    path("tasks/new/", views.task_create, name="task_create"),
    path("tasks/<int:pk>/edit/", views.task_edit, name="task_edit"),
    path("tasks/<int:pk>/delete/", views.task_delete, name="task_delete"),
    path("tasks/<int:pk>/done/", views.task_done, name="task_done"),

    path("workers/", views.worker_list, name="worker_list"),
    path("workers/new/", views.worker_create, name="worker_create"),
    path("workers/<int:pk>/edit/", views.worker_edit, name="worker_edit"),
    path("workers/<int:pk>/delete/", views.worker_delete, name="worker_delete"),

    path("materials/", views.material_list, name="material_list"),
    path("materials/new/", views.material_create, name="material_create"),
    path("materials/catalog/", views.material_catalog, name="material_catalog"),
    path("materials/catalog/new/", views.material_catalog_create, name="material_catalog_create"),
    path("materials/catalog/<int:pk>/edit/", views.material_catalog_edit, name="material_catalog_edit"),
    path("materials/catalog/<int:pk>/delete/", views.material_catalog_delete, name="material_catalog_delete"),
    path("materials/<int:pk>/edit/", views.material_edit, name="material_edit"),
    path("materials/<int:pk>/delete/", views.material_delete, name="material_delete"),

    path("expenses/", views.expense_list, name="expense_list"),
    path("expenses/new/", views.expense_create, name="expense_create"),
    path("expenses/<int:pk>/edit/", views.expense_edit, name="expense_edit"),
    path("expenses/<int:pk>/delete/", views.expense_delete, name="expense_delete"),

    path("reports/", views.report_list, name="report_list"),
    path("reports/export/", views.report_csv, name="report_csv"),

    path("timesheet/", views.timesheet_list, name="timesheet_list"),
    path("timesheet/new/", views.timesheet_create, name="timesheet_create"),
    path("timesheet/<int:pk>/edit/", views.timesheet_edit, name="timesheet_edit"),
    path("timesheet/<int:pk>/delete/", views.timesheet_delete, name="timesheet_delete"),
    path("payroll/", views.payroll, name="payroll"),
    path("payroll/post/", views.payroll_post, name="payroll_post"),

    path("my/", views.my_tasks, name="my_tasks"),
    path("my/tasks/<int:pk>/<str:status>/", views.my_task_status, name="my_task_status"),
    path("my/hours/", views.my_hours, name="my_hours"),
    path("my/hours/<int:pk>/delete/", views.my_hours_delete, name="my_hours_delete"),
    path("my/project/", views.my_project, name="my_project"),
    path("my/salary/", views.my_salary, name="my_salary"),

    path("settings/", views.app_settings, name="app_settings"),
]
