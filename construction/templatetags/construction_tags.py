from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    """Поточний рядок запиту GET із підміною параметрів (для пагінації зі збереженням фільтрів).

    Використання: <a href="?{% url_replace page=3 %}">
    """
    query = context["request"].GET.copy()
    for key, value in kwargs.items():
        query[key] = value
    return query.urlencode()


@register.inclusion_tag("construction/includes/budget_bar.html")
def budget_bar(project):
    """Смуга використання бюджету проєкту з відсотком (повторюється в кількох таблицях)."""
    return {"project": project}


@register.simple_tag
def money(value, digits=0):
    """Сума у гривнях: {% money project.budget %} -> «250 000 ₴»."""
    from django.template.defaultfilters import floatformat
    return f"{floatformat(value, f'{digits}g')} ₴"
