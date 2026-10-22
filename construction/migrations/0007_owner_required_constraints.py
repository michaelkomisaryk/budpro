import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Після data-міграції 0006 власник стає обов'язковим; додаються UniqueConstraint."""

    dependencies = [
        ("construction", "0006_assign_owners_and_roles"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="project",
            name="owner",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="projects",
                                    to=settings.AUTH_USER_MODEL, verbose_name="Власник (директор)"),
        ),
        migrations.AlterField(
            model_name="worker",
            name="owner",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="workers_owned",
                                    to=settings.AUTH_USER_MODEL, verbose_name="Власник (директор)"),
        ),
        migrations.AddConstraint(
            model_name="catalogitem",
            constraint=models.UniqueConstraint(
                fields=("name", "unit"), name="uniq_catalog_name_unit",
                violation_error_message="Така позиція (назва й одиниця виміру) вже є в каталозі."),
        ),
        migrations.AddConstraint(
            model_name="project",
            constraint=models.UniqueConstraint(
                fields=("owner", "name"), name="uniq_project_owner_name",
                violation_error_message="У вас уже є проєкт з такою назвою."),
        ),
    ]
