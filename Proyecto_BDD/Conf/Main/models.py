from django.conf import settings
from django.db import models

from .validators import validar_cedula


class Perfil(models.Model):
    """
    Datos adicionales de cada usuario.

    Antes existía el modelo Main.User (nombre, cédula, cargo), pero no estaba
    conectado al sistema de autenticación de Django: no tenía contraseña ni
    sesión, por eso no servía para iniciar sesión. Ahora el usuario es el de
    Django (auth.User: username, contraseña, nombre, apellido, correo) y aquí
    solo se guarda lo que le falta: la cédula.
    """
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='perfil'
    )
    cedula = models.CharField(max_length=10, unique=True, validators=[validar_cedula])

    class Meta:
        db_table = 'perfiles'
        verbose_name_plural = 'perfiles'

    def __str__(self):
        return f'{self.usuario.get_full_name() or self.usuario.username} ({self.cedula})'
