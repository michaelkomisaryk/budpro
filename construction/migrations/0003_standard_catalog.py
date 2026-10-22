from decimal import Decimal

from django.db import migrations

# (назва, одиниця виміру, орієнтовна ціна за одиницю, грн)
STANDARD_ITEMS = [
    ("Цемент М500 (мішок 50 кг)", "pcs", "195"),
    ("Цегла керамічна", "pcs", "12"),
    ("Газоблок 600×200×300", "pcs", "85"),
    ("Пісок річковий", "m3", "450"),
    ("Щебінь фракції 20–40", "m3", "780"),
    ("Бетон М300", "m3", "2650"),
    ("Арматура Ø12", "m", "42"),
    ("Дошка обрізна", "m3", "8500"),
    ("Профнастил С20", "m2", "310"),
    ("Гіпсокартон (лист)", "pcs", "260"),
    ("Утеплювач мінеральна вата", "m2", "190"),
    ("Плитка керамічна", "m2", "480"),
    ("Фарба фасадна", "l", "140"),
    ("Ґрунтовка глибокого проникнення", "l", "60"),
    ("Штукатурка гіпсова", "kg", "9"),
    ("Труба ПВХ каналізаційна", "m", "55"),
    ("Кабель ВВГнг 3×2,5", "m", "38"),
]


def add_standard_items(apps, schema_editor):
    CatalogItem = apps.get_model("construction", "CatalogItem")
    for name, unit, price in STANDARD_ITEMS:
        CatalogItem.objects.get_or_create(
            name=name, unit=unit, defaults={"unit_price": Decimal(price), "is_custom": False})


def remove_standard_items(apps, schema_editor):
    apps.get_model("construction", "CatalogItem").objects.filter(is_custom=False).delete()


class Migration(migrations.Migration):
    dependencies = [("construction", "0002_catalogitem")]
    operations = [migrations.RunPython(add_standard_items, remove_standard_items)]
