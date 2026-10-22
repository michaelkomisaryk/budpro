"""Ролі та доступ до даних.

Ролі:
* «Директор» - група з власними правами (view_finance_reports, manage_payroll) або суперкористувач.
  Керує лише СВОЇМИ даними: проєкт і працівник мають власника (owner), решта записів
  (завдання, матеріали, витрати, табель) належать власнику свого проєкту/працівника.
* «Працівник» - користувач, прив'язаний до запису Worker (кабінет /my/).
"""
from django.contrib.auth.models import Group, Permission

DIRECTOR_GROUP = "Директор"
WORKER_GROUP = "Працівник"

# Власні права директора (оголошені в Meta.permissions моделей Expense і WorkLog)
DIRECTOR_PERMISSIONS = [
    ("construction", "view_finance_reports"),
    ("construction", "manage_payroll"),
]

# модель -> шлях до власника-директора
OWNER_LOOKUPS = {
    "Project": "owner",
    "Worker": "owner",
    "Task": "project__owner",
    "Material": "project__owner",
    "Expense": "project__owner",
    "WorkLog": "worker__owner",
}


def is_director(user):
    """Директор: суперкористувач або член групи «Директор»."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=DIRECTOR_GROUP).exists()


def scope(queryset, user, lookup="owner"):
    """Залишає лише записи користувача (суперкористувач бачить усе)."""
    if user.is_superuser:
        return queryset
    return queryset.filter(**{lookup: user})


def for_user(model, user):
    """Усі записи моделі, до яких має доступ користувач."""
    queryset = model._default_manager.all()
    lookup = OWNER_LOOKUPS.get(model.__name__)
    return scope(queryset, user, lookup) if lookup else queryset


def sync_roles(apps=None):
    """Створює групи ролей і призначає директору власні права (викликається з міграції та реєстрації)."""
    group_model = apps.get_model("auth", "Group") if apps else Group
    permission_model = apps.get_model("auth", "Permission") if apps else Permission
    director, _ = group_model.objects.get_or_create(name=DIRECTOR_GROUP)
    group_model.objects.get_or_create(name=WORKER_GROUP)
    for app_label, codename in DIRECTOR_PERMISSIONS:
        permission = permission_model.objects.filter(
            content_type__app_label=app_label, codename=codename).first()
        if permission:
            director.permissions.add(permission)
    return director
