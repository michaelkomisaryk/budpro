# 1.3 Опис програмної реалізації (чернетка)

> Чернетка складена за кодом проєкту. Скріншоти Debug Toolbar та версію СУБД (`SELECT VERSION();`) додайте самі:
> автор чернетки перевіряв проєкт на MariaDB 10.11.14.

## 1. Структура проєкту
Проєкт `config` і застосунок `construction`. Ключові налаштування (`config/settings.py`):

| Параметр | Значення |
|---|---|
| `INSTALLED_APPS` | admin, auth, contenttypes, sessions, messages, staticfiles, `construction` (+ `debug_toolbar` при `DEBUG=1`) |
| `DATABASES` | `django.db.backends.mysql`; `NAME/USER/PASSWORD/HOST/PORT` з `os.environ` (файл `.env` через python-dotenv) |
| `MIDDLEWARE` | стандартні + власний `construction.middleware.RoleMiddleware` |
| Статика | `STATIC_URL = "static/"`; Bootstrap 5.3.3 — `construction/static/construction/vendor/bootstrap/`, власний CSS — `css/style.css` |
| `LOGIN_URL` | `construction:login` (`LOGIN_REDIRECT_URL = construction:dashboard`) |
| Пошта | `EMAIL_BACKEND` — консольний (скидання пароля) |
| Мова | `LANGUAGE_CODE = "uk"`, `TIME_ZONE = "Europe/Kyiv"` |

Змінні оточення: `SECRET_KEY`, `DEBUG`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` (шаблон — `.env.example`).
Залежності зафіксовано в `requirements.txt` (Django==5.2.18, PyMySQL==1.2.3, cryptography==46.0.6, python-dotenv==1.2.2, django-debug-toolbar==8.0.0).

## 2. Моделі
Сім моделей домену, `__str__()` у кожній. Власник запису — `ForeignKey` на `auth.User`.

| Модель | Ключові поля | Зв'язки та `on_delete` (обґрунтування) | Meta |
|---|---|---|---|
| `Project` | name, address, description (текст), budget (Decimal), start_date, end_date (дата), status (choices) | `owner` → User, **PROTECT** (акаунт директора з фінансовими даними не можна видалити випадково) | ordering `-created_at`; **UniqueConstraint** (owner, name); `get_absolute_url()` |
| `Task` | title, description, due_date, status (choices) | `project` → Project, **CASCADE** (завдання не існує без проєкту); `assignee` → Worker, **SET_NULL** (завдання лишається без виконавця); **ManyToMany** `materials` → Material, `related_name="tasks"` | ordering `due_date` |
| `Worker` | first_name, last_name, position (choices), phone, hourly_rate | `project` → Project, **SET_NULL** (працівник лишається в системі); `user` → User (OneToOne), **SET_NULL**; `owner` → User, **PROTECT** | ordering за прізвищем |
| `Material` | name, quantity, unit (choices), unit_price | `project` → Project, **CASCADE** | ordering `name` |
| `CatalogItem` | name, unit, unit_price, is_custom (булеве) | — (довідник, спільний) | **UniqueConstraint** (name, unit) |
| `Expense` | title, category (choices), amount, date, description | `project` → Project, **CASCADE** | **permissions**: `view_finance_reports` |
| `WorkLog` | date, hours, comment, rate (ставка на момент запису) | `worker` → Worker, **CASCADE**; `task` → Task, **SET_NULL** (години й зарплата зберігаються) | **permissions**: `manage_payroll` |

* `ProjectQuerySet.with_totals()` — одним запитом додає `spent_total`, `materials_total`, `tasks_total`, `tasks_done` (підзапити), тому у списках немає N+1.
* Міграції `0001`–`0007`. **Data-міграції (RunPython):** `0003_standard_catalog` (стандартний каталог матеріалів) та `0006_assign_owners_and_roles` (групи «Директор»/«Працівник», права, власники наявних записів, прибирання дублікатів каталогу).
* SQL для розділу 1.2 (діалект MySQL/MariaDB): `docs/sql/*.sql`, отримано через `python manage.py sqlmigrate construction <міграція>`.

## 3. Форми і валідація
| Форма | Тип | Правила та рівень |
|---|---|---|
| `ProjectForm` | ModelForm (поля перелічені явно, власника немає) | поле: `clean_name` — унікальність назви у власника; форма: `clean` — активний проєкт має мати бюджет > 0; модель: `Project.clean` — дата завершення не раніше початку |
| `TaskForm` | ModelForm | поле: `clean_title` (мін. 3 символи); форма: `clean` — матеріали мають належати проєкту завдання; вибір обмежений записами користувача; модель: виконавець з того ж проєкту |
| `WorkerForm` | ModelForm + логін/пароль | поле: `clean_username` (унікальність); форма: `clean` — пароль обов'язковий для нового акаунта, перевірка складності; поле моделі: **власний валідатор** `validate_phone` |
| `ExpenseForm` | ModelForm | поле: `clean_amount` > 0 |
| `MaterialForm`, `CatalogItemForm`, `WorkLogForm` | ModelForm | `WorkLogForm`: **власний валідатор** `validate_quarter_hour` (крок 0,25 год); модель: перевірки дати та завдання |
| `RegisterForm` | `UserCreationForm` | обов'язкові ім'я, прізвище, пошта; `clean_email` — унікальність |
| `ProjectFilterForm`, `TaskFilterForm`, `PeriodForm` | **`forms.Form` без моделі** (GET) | пошук і фільтри; `PeriodForm.clean` — «До» не раніше «Від» |

Власні валідатори — `construction/validators.py`. Усі повідомлення про помилки — українською.
Усі форми зміни даних мають `{% csrf_token %}`, зміни — лише POST із перенаправленням (Post/Redirect/Get).

## 4. Представлення
Клас обрано там, де є стандартний сценарій CRUD (список, картка, форма) — Generic Views дають готову пагінацію, обробку форм, PRG. Функції — для зведень і дій, що не є CRUD однієї моделі.

| Клас або функція | Маршрут (ім'я) | Що перевизначено і навіщо |
|---|---|---|
| `ProjectListView` | `project_list` | `get_queryset()` — фільтри через `ProjectFilterForm`, Q-пошук, `with_totals()`; `get_context_data()` — форма; `paginate_by = 8` |
| `ProjectDetailView` | `project_detail` | `get_queryset()` (суми), `get_context_data()` (завдання, працівники, матеріали, витрати) |
| `ProjectCreateView` | `project_create` | `form_valid()` (через `OwnerOnCreateMixin`) — **власник = request.user**; `get_success_url()` |
| `ProjectUpdateView` | `project_edit` | `OwnedMixin.get_queryset()` — лише свої; `get_form_kwargs()` — user |
| `ProjectDeleteView` | `project_delete` | видалення лише POST; свої записи |
| `Task*`, `Worker*`, `Material*`, `Expense*`, `Catalog*`, `Timesheet*` | див. таблицю URL | `ListView` (фільтри, пагінація) + `DetailView` (`BaseDetailView`, рядки з `detail_fields`) + Create/Update/Delete (базові класи з `mixins.py`) |
| `RegisterView` | `register` | `form_valid()` — додає в групу «Директор», входить |
| `dashboard` (FBV) | `dashboard` | зведення з кількох моделей, графік |
| `task_done`, `payroll_post` (FBV) | `task_done`, `payroll_post` | дія лише через POST |
| `report_list`, `report_csv`, `payroll` (FBV) | `report_list`, `report_csv`, `payroll` | розрахунки та експорт; права `view_finance_reports` / `manage_payroll` |
| `my_*` (FBV) | `my_tasks`, `my_hours`, `my_project`, `my_salary` | кабінет працівника |
| `app_settings` (FBV) | `app_settings` | дві форми на одній сторінці |

## 5. Маршрути (`app_name = "construction"`)
| Шаблон | Ім'я | Представлення |
|---|---|---|
| `login/` | `login` | клас `LoginView` |
| `logout/` | `logout` | клас `LogoutView` |
| `register/` | `register` | клас `RegisterView` |
| `password-reset/` | `password_reset` | клас `PasswordResetView` |
| `password-reset/sent/` | `password_reset_done` | клас `PasswordResetDoneView` |
| `password-reset/<uidb64>/<token>/` | `password_reset_confirm` | клас `PasswordResetConfirmView` |
| `password-reset/complete/` | `password_reset_complete` | клас `PasswordResetCompleteView` |
| `` | `dashboard` | функція `dashboard` |
| `projects/` | `project_list` | клас `ProjectListView` |
| `projects/new/` | `project_create` | клас `ProjectCreateView` |
| `projects/<int:pk>/` | `project_detail` | клас `ProjectDetailView` |
| `projects/<int:pk>/edit/` | `project_edit` | клас `ProjectUpdateView` |
| `projects/<int:pk>/delete/` | `project_delete` | клас `ProjectDeleteView` |
| `tasks/` | `task_list` | клас `TaskListView` |
| `tasks/new/` | `task_create` | клас `TaskCreateView` |
| `tasks/<int:pk>/` | `task_detail` | клас `TaskDetailView` |
| `tasks/<int:pk>/edit/` | `task_edit` | клас `TaskUpdateView` |
| `tasks/<int:pk>/delete/` | `task_delete` | клас `TaskDeleteView` |
| `tasks/<int:pk>/done/` | `task_done` | функція `task_done` |
| `workers/` | `worker_list` | клас `WorkerListView` |
| `workers/new/` | `worker_create` | клас `WorkerCreateView` |
| `workers/<int:pk>/` | `worker_detail` | клас `WorkerDetailView` |
| `workers/<int:pk>/edit/` | `worker_edit` | клас `WorkerUpdateView` |
| `workers/<int:pk>/delete/` | `worker_delete` | клас `WorkerDeleteView` |
| `materials/` | `material_list` | клас `MaterialListView` |
| `materials/new/` | `material_create` | клас `MaterialCreateView` |
| `materials/catalog/` | `material_catalog` | клас `CatalogListView` |
| `materials/catalog/new/` | `material_catalog_create` | клас `CatalogCreateView` |
| `materials/catalog/<int:pk>/` | `catalog_detail` | клас `CatalogDetailView` |
| `materials/catalog/<int:pk>/edit/` | `catalog_edit` | клас `CatalogUpdateView` |
| `materials/catalog/<int:pk>/delete/` | `catalog_delete` | клас `CatalogDeleteView` |
| `materials/<int:pk>/` | `material_detail` | клас `MaterialDetailView` |
| `materials/<int:pk>/edit/` | `material_edit` | клас `MaterialUpdateView` |
| `materials/<int:pk>/delete/` | `material_delete` | клас `MaterialDeleteView` |
| `expenses/` | `expense_list` | клас `ExpenseListView` |
| `expenses/new/` | `expense_create` | клас `ExpenseCreateView` |
| `expenses/<int:pk>/` | `expense_detail` | клас `ExpenseDetailView` |
| `expenses/<int:pk>/edit/` | `expense_edit` | клас `ExpenseUpdateView` |
| `expenses/<int:pk>/delete/` | `expense_delete` | клас `ExpenseDeleteView` |
| `reports/` | `report_list` | функція `report_list` |
| `reports/export/` | `report_csv` | функція `report_csv` |
| `timesheet/` | `timesheet_list` | клас `TimesheetListView` |
| `timesheet/new/` | `timesheet_create` | клас `TimesheetCreateView` |
| `timesheet/<int:pk>/` | `timesheet_detail` | клас `TimesheetDetailView` |
| `timesheet/<int:pk>/edit/` | `timesheet_edit` | клас `TimesheetUpdateView` |
| `timesheet/<int:pk>/delete/` | `timesheet_delete` | клас `TimesheetDeleteView` |
| `payroll/` | `payroll` | функція `payroll` |
| `payroll/post/` | `payroll_post` | функція `payroll_post` |
| `my/` | `my_tasks` | функція `my_tasks` |
| `my/tasks/<int:pk>/<str:status>/` | `my_task_status` | функція `my_task_status` |
| `my/hours/` | `my_hours` | функція `my_hours` |
| `my/hours/<int:pk>/delete/` | `my_hours_delete` | функція `my_hours_delete` |
| `my/project/` | `my_project` | функція `my_project` |
| `my/salary/` | `my_salary` | функція `my_salary` |
| `settings/` | `app_settings` | функція `app_settings` |

Конвертер `<int:pk>` використано для сторінок запису; у шаблонах і коді — лише `{% url %}` та `reverse()`.

## 6. Шаблони
```
construction/base.html            (Bootstrap + style.css; {% include %} _sidebar, _messages)
├── dashboard.html, project_list.html, project_detail.html, task_list.html, worker_list.html,
│   material_list.html, material_catalog.html, expense_list.html, timesheet_list.html, payroll.html,
│   reports.html, settings.html, my_tasks.html, my_hours.html, my_project.html, my_salary.html, no_profile.html
├── form.html (усі форми створення/редагування), confirm_delete.html, object_detail.html (картки записів)
└── includes/: _sidebar.html, _messages.html, _pagination.html, _filter_actions.html, budget_bar.html
registration/auth_base.html       (окремий каркас сторінок входу)
├── login.html, register.html, password_reset_form/done/confirm/complete.html
```
Власні теги (`templatetags/construction_tags.py`): `{% url_replace %}` (simple_tag, пагінація зі збереженням фільтрів), `{% budget_bar project %}` (inclusion_tag), `{% money %}` (simple_tag).

## 7. Ролі і доступ
| Роль | Що може | Де перевіряється |
|---|---|---|
| Анонім | лише вхід, реєстрація, скидання пароля | `LoginRequiredMixin` / `@login_required` → редірект на `construction:login` |
| Директор (група «Директор») | CRUD **своїх** проєктів, працівників, завдань, матеріалів, витрат, табеля; каталог | `DirectorMixin.has_permission()` (`request.is_director` з `RoleMiddleware`); `OwnedMixin.get_queryset()` — чужий запис = 404; форми обмежують вибір записами користувача |
| Директор + `view_finance_reports` | звіти, CSV | `@director_required(perm=...)` у `report_list`, `report_csv` |
| Директор + `manage_payroll` | зарплати, внесення у витрати | `@director_required(perm=...)` у `payroll`, `payroll_post` |
| Суперкористувач | усе (адмін) | `access.scope()` не фільтрує; `has_perm` завжди True |
| Працівник | свої завдання, години, зарплата, проєкт без бюджету | `@worker_required` + вибірки `assignee=request.worker` / `worker=request.worker` |

Кнопки в шаблонах приховуються додатково (`perms.construction.*`), але рішення ухвалює сервер.

## 8. Оптимізація запитів (Д5)
| Сторінка | Проблема (N+1) | Рішення |
|---|---|---|
| Список проєктів (5 проєктів у демо) | `spent`, `budget_percent`, `progress` — окремі запити на кожен проєкт | `with_totals()`: підзапити в одному `SELECT` |
| Головна, звіти | те саме для `alerts`/рядків звіту | `with_totals()` |
| Завдання, працівники, матеріали, витрати, табель | доступ до `project`, `assignee`, `user`, `worker` у шаблоні | `select_related(...)` |
| Зарплати | запит «чи внесено» на кожного працівника | один запит `title__in` і словник |

Вимірювання (`CaptureQueriesContext`, MariaDB 10.11, демо-дані: 5 проєктів, 18 завдань, 8 працівників, 19 витрат, 132 записи табеля):

| Сценарій | До | Після |
|---|---|---|
| Суми по 5 проєктах (рядки списку) | 16 запитів, ≈10 мс | **1 запит**, ≈3 мс |

Тест `test_project_list_has_no_n_plus_one` перевіряє, що кількість запитів сторінки не залежить від кількості проєктів.
**Скріншоти Debug Toolbar (вкладка SQL) до/після зробіть самі:** `DEBUG=1`, відкрийте `/projects/`.

## 9. Відповідність вимогам
| Вимога | Де виконано |
|---|---|
| В1.1–В1.3 | `requirements.txt` (версії зафіксовано), git, `README.md` |
| В1.4 | `app_name`, імена маршрутів, `{% url %}`/`reverse()` |
| В2.1–В2.2 | MySQL/MariaDB; `.env` у `.gitignore`, `.env.example` без значень; `SECRET_KEY` з env |
| В3.1–В3.5 | 7 моделей, owner FK, choices/числа/дати/булеве, міграції + 2 data-міграції, ModelAdmin, `seed_demo` |
| В4.1–В4.3 | `base.html`, `{% include %}`, Bootstrap + `style.css`, 3 власні теги |
| В5.1–В5.4 | ModelForm, 3 `forms.Form`, власні валідатори, `clean_*`/`clean`, CSRF, PRG |
| В6.1–В6.5 | Generic Views для всіх сутностей, FBV, `paginate_by`, `get_absolute_url`, `<int:pk>` |
| В7.1–В7.5 | реєстрація, вхід/вихід (POST), `form_valid` власник, міксини, ролі через групи й права |
| В8.1–В8.2 | немає `raw()`, `|safe`, `mark_safe` |
| Д1–Д7 | M2M `related_name`; `on_delete`; ordering/verbose_name/UniqueConstraint; Q, annotate, aggregate; select_related + Debug Toolbar; Meta.permissions + groups; middleware, зміна й скидання пароля |
