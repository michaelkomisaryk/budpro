from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError

from .access import WORKER_GROUP, for_user
from .models import CatalogItem, Expense, Material, Project, Task, WorkLog, Worker

AUTOSUBMIT = {"data-autosubmit": "1"}


def style_fields(form):
    """Додає CSS-класи до полів форми, щоб вони виглядали однаково на всьому сайті."""
    for field in form.fields.values():
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs["class"] = "check"
        elif isinstance(field.widget, forms.Select):
            field.widget.attrs["class"] = "select"
        elif isinstance(field, forms.DateField):
            attrs = dict(field.widget.attrs)
            field.widget = forms.DateInput(attrs=attrs | {"type": "date"}, format="%Y-%m-%d")
            field.widget.attrs["class"] = "input"
        else:
            field.widget.attrs["class"] = "input"
        if isinstance(field, forms.DecimalField):
            field.widget.attrs["min"] = "0"


class StyledModelForm(forms.ModelForm):
    """Базова ModelForm: однаковий вигляд полів і доступ до користувача (user).

    Поля власника (owner) у формах немає: його ставить view у form_valid().
    user потрібен, щоб у списках вибору були лише ЙОГО проєкти, працівники, завдання.
    """

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        style_fields(self)

    def limit(self, field_name, model):
        """Обмежує вибір у полі записами, до яких має доступ користувач."""
        if self.user is not None and field_name in self.fields:
            self.fields[field_name].queryset = for_user(model, self.user)
        return self.fields.get(field_name)


class ProjectForm(StyledModelForm):
    class Meta:
        model = Project
        fields = ["name", "address", "description", "budget", "start_date", "end_date", "status"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def clean_name(self):
        """Рівень поля: назва проєкту унікальна серед проєктів цього директора."""
        name = self.cleaned_data["name"].strip()
        owner = self.instance.owner if self.instance.owner_id else self.user
        if owner is not None:
            clash = Project.objects.filter(owner=owner, name__iexact=name).exclude(pk=self.instance.pk)
            if clash.exists():
                raise ValidationError("У вас уже є проєкт з такою назвою.")
        return name

    def clean(self):
        """Рівень форми: правила, що залежать від кількох полів."""
        data = super().clean()
        status, budget = data.get("status"), data.get("budget")
        if status == Project.Status.ACTIVE and budget is not None and budget <= 0:
            self.add_error("budget", "Активний проєкт має мати бюджет більший за нуль.")
        return data


class TaskForm(StyledModelForm):
    class Meta:
        model = Task
        fields = ["project", "title", "description", "assignee", "due_date", "status", "materials"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3}),
                   "materials": forms.SelectMultiple(attrs={"size": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit("project", Project)
        self.limit("assignee", Worker)
        self.limit("materials", Material)
        self.fields["assignee"].empty_label = "— не призначено —"
        self.fields["assignee"].queryset = self.fields["assignee"].queryset.select_related("project")
        self.fields["assignee"].label_from_instance = (
            lambda w: f"{w.full_name} — {w.project.name if w.project else 'без проєкту'}")
        self.fields["materials"].queryset = self.fields["materials"].queryset.select_related("project")
        self.fields["materials"].label_from_instance = lambda m: f"{m.name} ({m.project.name})"
        self.fields["materials"].help_text = "Необов'язково. Утримуйте Ctrl, щоб вибрати кілька матеріалів."

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if len(title) < 3:
            raise ValidationError("Назва завдання має містити щонайменше 3 символи.")
        return title

    def clean(self):
        data = super().clean()
        project, materials = data.get("project"), data.get("materials")
        if project and materials:
            foreign = [m.name for m in materials if m.project_id != project.pk]
            if foreign:
                self.add_error("materials", "Матеріали мають належати проєкту завдання: " + ", ".join(foreign) + ".")
        return data


class WorkerForm(StyledModelForm):
    username = forms.CharField(
        required=False, max_length=150, label="Логін для входу",
        help_text="Заповніть, щоб працівник міг заходити на сайт під своїм логіном.")
    password = forms.CharField(
        required=False, label="Пароль", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Для нового акаунта обов'язковий. Для наявного заповніть лише щоб змінити пароль.")

    class Meta:
        model = Worker
        fields = ["first_name", "last_name", "position", "phone", "project", "hourly_rate"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit("project", Project)
        self.fields["project"].empty_label = "— не прикріплено —"
        if self.instance.user_id:
            self.fields["username"].initial = self.instance.user.username

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if username:
            taken = User.objects.filter(username__iexact=username)
            if self.instance.user_id:
                taken = taken.exclude(pk=self.instance.user_id)
            if taken.exists():
                raise ValidationError("Такий логін уже зайнятий.")
        return username

    def clean(self):
        data = super().clean()
        username, password = data.get("username"), data.get("password")
        if username and not self.instance.user_id and not password:
            self.add_error("password", "Вкажіть пароль для нового акаунта.")
        if password:
            try:
                password_validation.validate_password(password)
            except ValidationError as error:
                self.add_error("password", error)
        return data

    def save(self, commit=True):
        worker = super().save(commit)
        username, password = self.cleaned_data.get("username"), self.cleaned_data.get("password")
        if commit and username:
            user = worker.user or User(first_name=worker.first_name, last_name=worker.last_name)
            user.username = username
            if password:
                user.set_password(password)
            user.save()
            group, _ = Group.objects.get_or_create(name=WORKER_GROUP)
            user.groups.add(group)
            if worker.user_id != user.pk:
                worker.user = user
                worker.save()
        return worker


class CatalogSelect(forms.Select):
    """Список каталогу: до кожного пункту додає назву, одиницю та ціну для автозаповнення (JS)."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        item = getattr(value, "instance", None)
        if item:
            option["attrs"].update({"data-name": item.name, "data-unit": item.unit,
                                    "data-price": str(item.unit_price)})
        return option


class MaterialForm(StyledModelForm):
    catalog_item = forms.ModelChoiceField(
        queryset=CatalogItem.objects.all(), required=False, widget=CatalogSelect,
        label="Матеріал з каталогу", empty_label="— свій матеріал (ввести вручну) —",
        help_text="Оберіть позицію: назва, одиниця та ціна підставляться самі, їх можна змінити.")
    save_to_catalog = forms.BooleanField(
        required=False, label="Зберегти як свою позицію в каталозі",
        help_text="Матеріал з'явиться в списку каталогу, і наступного разу його можна буде просто вибрати.")
    field_order = ["project", "catalog_item", "name", "quantity", "unit", "unit_price", "save_to_catalog"]

    class Meta:
        model = Material
        fields = ["project", "name", "quantity", "unit", "unit_price"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit("project", Project)
        self.fields["catalog_item"].label_from_instance = (
            lambda item: f"{item.name} — {item.unit_price} ₴ / {item.get_unit_display()}"
                         f"{' · своя' if item.is_custom else ''}")

    def save(self, commit=True):
        material = super().save(commit)
        if commit and self.cleaned_data.get("save_to_catalog") and not self.cleaned_data.get("catalog_item"):
            CatalogItem.objects.get_or_create(
                name=material.name, unit=material.unit, defaults={"unit_price": material.unit_price})
        return material


class CatalogItemForm(StyledModelForm):
    class Meta:
        model = CatalogItem
        fields = ["name", "unit", "unit_price"]


class ExpenseForm(StyledModelForm):
    class Meta:
        model = Expense
        fields = ["project", "title", "category", "amount", "date", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit("project", Project)

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise ValidationError("Сума витрати має бути більшою за нуль.")
        return amount


class WorkLogForm(StyledModelForm):
    class Meta:
        model = WorkLog
        fields = ["worker", "task", "date", "hours", "comment"]

    def __init__(self, *args, worker=None, **kwargs):
        """Якщо передано worker (форма працівника): поле «Працівник» ховається, завдання - лише його."""
        super().__init__(*args, **kwargs)
        self.fields["hours"].widget.attrs.update({"step": "0.25", "min": "0.25", "max": "24"})
        self.limit("worker", Worker)
        self.limit("task", Task)
        self.fields["task"].queryset = self.fields["task"].queryset.select_related("project")
        self.fields["task"].label_from_instance = lambda t: f"{t.title} — {t.project.name}"
        self.fields["worker"].label_from_instance = lambda w: w.full_name
        if worker:
            del self.fields["worker"]
            self.fields["task"].queryset = worker.tasks.select_related("project")
            self.fields["task"].empty_label = "— оберіть завдання —"


class ProfileForm(StyledModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        labels = {"first_name": "Ім'я", "last_name": "Прізвище", "email": "Електронна пошта"}


class RegisterForm(UserCreationForm):
    """Реєстрація нового директора (UserCreationForm + ім'я та пошта)."""

    email = forms.EmailField(required=True, label="Електронна пошта",
                             error_messages={"required": "Вкажіть електронну пошту.",
                                             "invalid": "Введіть коректну адресу електронної пошти."})

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")
        labels = {"first_name": "Ім'я", "last_name": "Прізвище"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Користувач з такою електронною поштою вже зареєстрований.")
        return email


# ---------------------------------------------------------------- форми без моделі (пошук і фільтри, GET)
PROJECT_SORTS = {
    "new": ("-start_date", "Дата початку: спочатку нові"),
    "old": ("start_date", "Дата початку: спочатку старі"),
    "budget_desc": ("-budget", "Бюджет: від більшого"),
    "budget_asc": ("budget", "Бюджет: від меншого"),
}


class ProjectFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Пошук за назвою або адресою", max_length=100,
                        widget=forms.TextInput(attrs={"placeholder": "Введіть назву проєкту"}))
    status = forms.ChoiceField(required=False, label="Статус", widget=forms.Select(attrs=AUTOSUBMIT),
                               choices=[("", "Усі статуси")] + list(Project.Status.choices))
    sort = forms.ChoiceField(required=False, label="Сортування", widget=forms.Select(attrs=AUTOSUBMIT),
                             choices=[(key, value[1]) for key, value in PROJECT_SORTS.items()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)

    def clean_q(self):
        return self.cleaned_data["q"].strip()


class TaskFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Пошук за назвою", max_length=100,
                        widget=forms.TextInput(attrs={"placeholder": "Назва завдання"}))
    project = forms.ModelChoiceField(required=False, label="Проєкт", queryset=Project.objects.none(),
                                     empty_label="Усі проєкти", widget=forms.Select(attrs=AUTOSUBMIT))
    assignee = forms.ModelChoiceField(required=False, label="Виконавець", queryset=Worker.objects.none(),
                                      empty_label="Усі виконавці", widget=forms.Select(attrs=AUTOSUBMIT))
    status = forms.ChoiceField(required=False, label="Статус", widget=forms.Select(attrs=AUTOSUBMIT),
                               choices=[("", "Усі статуси")] + list(Task.Status.choices))

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = for_user(Project, user)
        self.fields["assignee"].queryset = for_user(Worker, user)
        self.fields["assignee"].label_from_instance = lambda w: w.full_name
        style_fields(self)


class PeriodForm(forms.Form):
    """Період «від - до» для витрат і звітів."""

    date_from = forms.DateField(required=False, label="Від")
    date_to = forms.DateField(required=False, label="До")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)

    def clean(self):
        data = super().clean()
        start, end = data.get("date_from"), data.get("date_to")
        if start and end and end < start:
            raise ValidationError("Дата «До» не може бути раніше за дату «Від».")
        return data
