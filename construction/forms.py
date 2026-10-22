from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import CatalogItem, Expense, Material, Project, Task, WorkLog, Worker


def style_fields(form):
    """Додає CSS-класи до полів форми, щоб вони виглядали однаково на всьому сайті."""
    for field in form.fields.values():
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs["class"] = "check"
        elif isinstance(field.widget, forms.Select):
            field.widget.attrs["class"] = "select"
        elif isinstance(field, forms.DateField):
            field.widget = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
            field.widget.attrs["class"] = "input"
        else:
            field.widget.attrs["class"] = "input"
        if isinstance(field, forms.DecimalField):
            field.widget.attrs["min"] = "0"


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self)


class ProjectForm(StyledModelForm):
    class Meta:
        model = Project
        fields = ["name", "address", "description", "budget", "start_date", "end_date", "status"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class TaskForm(StyledModelForm):
    class Meta:
        model = Task
        fields = ["project", "title", "description", "assignee", "due_date", "status"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].empty_label = "— не призначено —"
        self.fields["assignee"].queryset = Worker.objects.select_related("project")
        self.fields["assignee"].label_from_instance = (
            lambda w: f"{w.full_name} — {w.project.name if w.project else 'без проєкту'}")


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


class WorkLogForm(StyledModelForm):
    class Meta:
        model = WorkLog
        fields = ["worker", "task", "date", "hours", "comment"]

    def __init__(self, *args, worker=None, **kwargs):
        """Якщо передано worker (форма працівника): поле «Працівник» ховається, завдання - лише його."""
        super().__init__(*args, **kwargs)
        self.fields["hours"].widget.attrs.update({"step": "0.25", "min": "0.25", "max": "24"})
        self.fields["task"].queryset = Task.objects.select_related("project")
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
