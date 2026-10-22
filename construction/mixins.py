"""Перевірка ролей і доступу (сервер), спільна поведінка Generic Views."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import CreateView, DeleteView, DetailView, UpdateView

from .access import OWNER_LOOKUPS, scope
from .models import Worker


def safe_next(request, default_url):
    """Адреса повернення з параметра next (лише всередині сайту)."""
    url = request.POST.get("next") or request.GET.get("next") or ""
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}):
        return url
    return default_url


# ---------------------------------------------------------------- ролі: декоратори для function-based view
def director_required(view=None, *, perm=None):
    """Сторінка лише для директора (і, за потреби, з потрібним правом perm).

    Працівника переспрямовує в його кабінет, директора без права - на головну.
    """
    def decorator(func):
        @login_required
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if not request.is_director:
                messages.error(request, "Ця сторінка доступна лише директору.")
                return redirect("construction:my_tasks")
            if perm and not request.user.has_perm(perm):
                messages.error(request, "У вас немає права на цю дію.")
                return redirect("construction:dashboard")
            return func(request, *args, **kwargs)
        return wrapper
    return decorator(view) if view else decorator


def worker_required(view):
    """Сторінка кабінету працівника. У request.worker лежить його запис."""
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.is_director:
            return redirect("construction:dashboard")
        worker = Worker.objects.select_related("project").filter(user=request.user).first()
        if worker is None:
            return render(request, "construction/no_profile.html")
        request.worker = worker
        return view(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------- ролі та власник: міксини для class-based view
class DirectorMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Доступ лише для директора (+ необов'язкове право permission_required)."""
    permission_required = ()

    def has_permission(self):
        return self.request.is_director and self.request.user.has_perms(self.get_permission_required())

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()  # перенаправлення на вхід
        if not self.request.is_director:
            messages.error(self.request, "Ця сторінка доступна лише директору.")
            return redirect("construction:my_tasks")
        messages.error(self.request, "У вас немає права на цю дію.")
        return redirect("construction:dashboard")


class OwnedMixin:
    """Залишає в queryset лише записи свого директора: чужий запис недоступний навіть за прямим URL (404)."""

    def get_queryset(self):
        queryset = super().get_queryset()
        lookup = OWNER_LOOKUPS.get(queryset.model.__name__)
        return scope(queryset, self.request.user, lookup) if lookup else queryset


class OwnerOnCreateMixin:
    """Власник запису ставиться на сервері у form_valid(), а не вибирається у формі."""

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class InitialFromQueryMixin:
    """Підставляє у форму значення з адреси, наприклад ?project=3 або ?worker=5."""
    initial_params = ()

    def get_initial(self):
        initial = super().get_initial()
        for name in self.initial_params:
            value = self.request.GET.get(name, "")
            if value.isdigit():
                initial[name] = value
        return initial


# ---------------------------------------------------------------- спільні базові класи CRUD
class PageContextMixin:
    title = ""
    back = ""  # ім'я маршруту списку

    def back_url(self):
        return safe_next(self.request, reverse(f"construction:{self.back}"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(title=self.title, cancel_url=self.back_url(),
                       next=self.request.POST.get("next") or self.request.GET.get("next", ""))
        return context

    def get_success_url(self):
        return self.back_url()


class FormPageMixin(PageContextMixin):
    template_name = "construction/form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user  # форма обмежує вибір записами цього користувача
        return kwargs


class BaseCreateView(DirectorMixin, FormPageMixin, SuccessMessageMixin, InitialFromQueryMixin, CreateView):
    success_message = "Запис створено."


class BaseUpdateView(DirectorMixin, OwnedMixin, FormPageMixin, SuccessMessageMixin, UpdateView):
    success_message = "Зміни збережено."


class BaseDeleteView(DirectorMixin, OwnedMixin, PageContextMixin, SuccessMessageMixin, DeleteView):
    """Підтвердження на GET, видалення лише POST-запитом (Post/Redirect/Get)."""
    template_name = "construction/confirm_delete.html"
    text = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(obj=self.object, text=self.text)
        return context

    def get_success_message(self, cleaned_data):
        return f"«{self.object}» видалено."


class BaseDetailView(DirectorMixin, OwnedMixin, DetailView):
    """Картка запису: рядки «назва - значення» беруться з detail_fields."""
    template_name = "construction/object_detail.html"
    title = ""
    back = ""
    edit = ""
    delete = ""
    detail_fields = ()  # (підпис, ім'я атрибута або функція від об'єкта)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = []
        for label, source in self.detail_fields:
            value = source(self.object) if callable(source) else getattr(self.object, source)
            if callable(value):
                value = value()
            rows.append({"label": label, "value": value,
                         "url": value.get_absolute_url() if hasattr(value, "get_absolute_url") else ""})
        context.update(title=self.title or str(self.object), rows=rows,
                       back_url=reverse(f"construction:{self.back}"),
                       edit_url=reverse(f"construction:{self.edit}", args=[self.object.pk]),
                       delete_url=reverse(f"construction:{self.delete}", args=[self.object.pk]))
        return context
