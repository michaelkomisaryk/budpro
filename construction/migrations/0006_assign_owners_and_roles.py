"""Data-міграція: ролі, власники наявних записів, прибирання дублікатів каталогу."""
from django.contrib.auth.management import create_permissions
from django.db import migrations

from construction.access import DIRECTOR_GROUP, WORKER_GROUP, sync_roles


def forwards(apps, schema_editor):
    # права Meta.permissions створюються лише після міграцій - створюємо їх тут, щоб призначити групі
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    director_group = sync_roles(apps)
    User = apps.get_model("auth", "User")
    Group = apps.get_model("auth", "Group")
    Project = apps.get_model("construction", "Project")
    Worker = apps.get_model("construction", "Worker")
    CatalogItem = apps.get_model("construction", "CatalogItem")

    # попередні директори (is_staff) стають членами групи «Директор»
    for user in User.objects.filter(is_staff=True):
        user.groups.add(director_group)
    worker_group = Group.objects.get(name=WORKER_GROUP)
    for worker in Worker.objects.exclude(user=None).select_related("user"):
        worker.user.groups.add(worker_group)

    # наявні проєкти й працівники без власника переходять першому директору
    orphans = Project.objects.filter(owner=None).exists() or Worker.objects.filter(owner=None).exists()
    if orphans:
        owner = (User.objects.filter(is_superuser=True).order_by("id").first()
                 or User.objects.filter(is_staff=True).order_by("id").first())
        if owner is None:
            owner = User.objects.create(username="director", is_staff=True, password="!")
            owner.groups.add(director_group)
        Project.objects.filter(owner=None).update(owner=owner)
        Worker.objects.filter(owner=None).update(owner=owner)

    # дублікати каталогу (однакові назва й одиниця) перед додаванням UniqueConstraint
    seen = set()
    for item in CatalogItem.objects.order_by("id"):
        key = (item.name, item.unit)
        if key in seen:
            item.delete()
        else:
            seen.add(key)


def backwards(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=[DIRECTOR_GROUP, WORKER_GROUP]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("construction", "0005_owner_m2m_permissions"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
