"""
Roles de la aplicación.

Se usan los Grupos de Django (django.contrib.auth.models.Group):
- "Administrador": registra, edita y elimina artistas y canciones.
- "Usuario": crea sus propias playlists y las visualiza.

Un superusuario (python manage.py createsuperuser) se trata siempre como
Administrador.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

GRUPO_ADMIN = 'Administrador'
GRUPO_USUARIO = 'Usuario'


def es_administrador(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    # Se guarda el resultado en el objeto para no consultar la BD varias
    # veces en la misma petición.
    if not hasattr(user, '_es_admin'):
        user._es_admin = user.groups.filter(name=GRUPO_ADMIN).exists()
    return user._es_admin


def solo_administrador(vista):
    """
    Decorador: exige sesión iniciada y rol Administrador.
    Sin sesión -> redirige al login. Con sesión pero sin rol -> error 403.
    """
    @login_required
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not es_administrador(request.user):
            raise PermissionDenied('Esta acción es solo para administradores.')
        return vista(request, *args, **kwargs)
    return envoltura
