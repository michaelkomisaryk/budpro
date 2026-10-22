from .access import is_director


class RoleMiddleware:
    """Власний middleware: один раз за запит визначає роль користувача.

    Записує в request.is_director (True/False) - view, декоратори та шаблони не роблять
    повторних запитів до групи.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        request.is_director = bool(user is not None and is_director(user))
        return self.get_response(request)
