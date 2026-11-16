from .roles import es_administrador


def rol(request):
    """Disponible en todas las plantillas: {% if es_admin %} ... {% endif %}"""
    return {'es_admin': es_administrador(request.user)}
