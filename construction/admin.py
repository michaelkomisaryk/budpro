from django.contrib import admin

from .models import CatalogItem, Expense, Material, Project, Task, WorkLog, Worker


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "status", "budget", "start_date", "end_date")
    list_filter = ("status",)
    search_fields = ("name", "address")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "assignee", "status", "due_date")
    list_filter = ("status", "project")
    search_fields = ("title",)


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "position", "phone", "project", "hourly_rate", "user")
    list_filter = ("position", "project")
    search_fields = ("first_name", "last_name")


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "quantity", "unit", "unit_price")
    list_filter = ("project", "unit")
    search_fields = ("name",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "category", "amount", "date")
    list_filter = ("category", "project")
    search_fields = ("title",)
    date_hierarchy = "date"


@admin.register(CatalogItem)
class CatalogItemAdmin(admin.ModelAdmin):
    list_display = ("name", "unit", "unit_price", "is_custom")
    list_filter = ("is_custom", "unit")
    search_fields = ("name",)


@admin.register(WorkLog)
class WorkLogAdmin(admin.ModelAdmin):
    list_display = ("worker", "task", "date", "hours", "rate")
    list_filter = ("worker", "date")
    date_hierarchy = "date"
