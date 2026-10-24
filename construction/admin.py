from django.contrib import admin

from .models import CatalogItem, Expense, Material, Project, Task, WorkLog, Worker


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "status", "budget", "start_date", "end_date", "owner")
    list_filter = ("status", "owner")
    search_fields = ("name", "address")
    list_select_related = ("owner",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "assignee", "status", "due_date")
    list_filter = ("status", "project")
    search_fields = ("title",)
    list_select_related = ("project", "assignee")
    filter_horizontal = ("materials",)


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "position", "phone", "project", "hourly_rate", "user", "owner")
    list_filter = ("position", "project", "owner")
    search_fields = ("first_name", "last_name")
    list_select_related = ("project", "user", "owner")


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "quantity", "unit", "unit_price")
    list_filter = ("project", "unit")
    search_fields = ("name",)
    list_select_related = ("project",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "category", "amount", "date")
    list_filter = ("category", "project")
    search_fields = ("title",)
    date_hierarchy = "date"
    list_select_related = ("project",)


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
    list_select_related = ("worker", "task")
