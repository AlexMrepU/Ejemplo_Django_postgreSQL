from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import Perfil


class PerfilInline(admin.StackedInline):
    model = Perfil
    can_delete = False


# Se reemplaza el admin de usuarios de Django para mostrar también la cédula.
# Para convertir a alguien en Administrador: editar el usuario y agregarlo
# al grupo "Administrador".
admin.site.unregister(User)


@admin.register(User)
class UsuarioAdmin(UserAdmin):
    inlines = [PerfilInline]
    list_display = ('username', 'first_name', 'last_name', 'email', 'roles', 'is_active')
    list_filter = ('groups', 'is_active', 'is_superuser')

    @admin.display(description='Roles')
    def roles(self, obj):
        return ', '.join(g.name for g in obj.groups.all()) or '-'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('groups')


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ('cedula', 'usuario')
    search_fields = ('cedula', 'usuario__username', 'usuario__first_name', 'usuario__last_name')
