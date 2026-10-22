def roles(request):
    """Додає в усі шаблони прапорець is_director (його виставляє RoleMiddleware)."""
    return {"is_director": getattr(request, "is_director", False)}
