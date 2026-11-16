from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import Group
from django.db import transaction
from django.shortcuts import redirect, render

from .forms import RegistroForm
from .models import Perfil
from .roles import GRUPO_USUARIO


def registro(request):
    """
    Registro público. Toda cuenta creada aquí recibe el rol "Usuario".
    El rol "Administrador" solo lo asigna un superusuario desde /admin/,
    para que nadie pueda darse permisos a sí mismo.
    """
    if request.user.is_authenticated:
        return redirect('inicio')

    form = RegistroForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        # atomic: si falla el perfil, tampoco se crea el usuario.
        with transaction.atomic():
            usuario = form.save()
            Perfil.objects.create(usuario=usuario, cedula=form.cleaned_data['cedula'])
            grupo, _ = Group.objects.get_or_create(name=GRUPO_USUARIO)
            usuario.groups.add(grupo)

        login(request, usuario)
        messages.success(request, f'Bienvenido, {usuario.first_name}. Su cuenta fue creada.')
        return redirect('inicio')

    return render(request, 'registration/registro.html', {'form': form})
