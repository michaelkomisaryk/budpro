# БудПроєкт

Система автоматизації планування, контролю та супроводу будівельних проєктів.
Django 5.2 + **MySQL** (перевірено на MariaDB 10.11.14; сумісна з MySQL 8.0) + Bootstrap 5.3 + власний CSS.

## Вимоги
* Python 3.12
* MySQL 8.0+ або MariaDB 10.6+ (версію, на якій ви запускаєте, вкажіть у звіті: `SELECT VERSION();`)

## Швидкий запуск
```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
```
1. Створіть базу в MySQL:
   `CREATE DATABASE construction_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`
2. Скопіюйте `.env.example` у `.env` і заповніть значення (файл `.env` у git не потрапляє).
3. `python manage.py migrate`
4. Демо-дані (необов'язково): `python manage.py seed_demo`
5. `python manage.py runserver` і відкрийте http://127.0.0.1:8000/

### Змінні оточення (`.env`)
| Змінна | Призначення | Приклад |
|---|---|---|
| `SECRET_KEY` | секретний ключ Django | довгий випадковий рядок |
| `DEBUG` | режим розробки (`1` — увімкнено) | `1` |
| `DB_NAME` | назва бази | `construction_db` |
| `DB_USER` | користувач MySQL | `root` |
| `DB_PASSWORD` | пароль користувача | — |
| `DB_HOST` | хост | `127.0.0.1` |
| `DB_PORT` | порт | `3306` |

### Облікові записи після `seed_demo`
| Роль | Логін / пароль | Що бачить |
|---|---|---|
| Директор (суперкористувач) | `admin` / `admin12345` | усі дані |
| Директор | `director2` / `director12345` | лише свої дані (1 проєкт) |
| Працівник | `sklyar`, `koval`, `melnyk`, `boyko`… / `worker12345` | свій кабінет `/my/` |

Власний акаунт директора можна створити на сторінці `/register/` або командою `createsuperuser`.

## Ролі та доступ
| Роль | Як визначається | Може |
|---|---|---|
| **Директор** | група «Директор» або суперкористувач | повний CRUD **своїх** проєктів, працівників, завдань, матеріалів, витрат, табеля |
| **Директор + право** `view_finance_reports` | право групи «Директор» | сторінка «Звіти» й експорт CSV |
| **Директор + право** `manage_payroll` | право групи «Директор» | сторінка «Зарплати» та внесення зарплати у витрати |
| **Працівник** | запис `Worker` з акаунтом (група «Працівник») | кабінет `/my/`: свої завдання, години, зарплата |

Перевірка ролей і власника виконується **на сервері** (`construction/mixins.py`, `construction/access.py`);
чужий запис дає 404. Групи й права створює data-міграція `0006_assign_owners_and_roles`.

## Тести та Debug Toolbar
```bash
python manage.py test construction     # потрібен користувач MySQL з правом CREATE DATABASE
```
У режимі `DEBUG=1` підключається Django Debug Toolbar (панель праворуч на сторінках): вкладка SQL показує кількість запитів.

## Структура
```
config/                 налаштування (settings.py), корінь URL, PyMySQL у __init__.py
construction/
    models.py           Project, Task, Worker, Material, CatalogItem, Expense, WorkLog
    forms.py            ModelForm, форми без моделі (фільтри), реєстрація
    validators.py       власні валідатори
    views.py            Generic Views (CRUD) і function-based views (зведення, звіти, кабінет)
    mixins.py           ролі, власник, базові класи CRUD
    access.py           ролі, групи, права, scope за власником
    middleware.py       RoleMiddleware
    templatetags/       власні DTL-теги
    templates/          base.html, includes/, registration/
    static/construction/{css,js,vendor/bootstrap}
    migrations/         0003 і 0006 — data-міграції (RunPython)
    management/commands/seed_demo.py
    tests.py
docs/                   текст до підрозділу 1.3 та SQL (sqlmigrate)
```

## Основні адреси
Усі маршрути мають `app_name = "construction"` і імена (`{% url 'construction:project_list' %}`).
Повна таблиця — у `docs/opys_1_3.md`.

## Облік
Матеріали (кількість × ціна) — облік матеріалів проєкту. Фактичні гроші вносяться окремо на сторінці «Витрати»;
контроль бюджету рахується лише за витратами, тому одна покупка не враховується двічі.
Зарплата = сума (години × ставка на момент запису); кнопка «внести у витрати» створює витрату категорії «Зарплата».
Після оновлення коду виконуйте `python manage.py migrate`.
