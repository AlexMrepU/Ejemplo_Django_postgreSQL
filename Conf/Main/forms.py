from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Perfil
from .validators import validar_cedula


class EstiloMixin:
    """Clase de Bootstrap en todos los campos."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'form-control')


class LoginForm(EstiloMixin, AuthenticationForm):
    pass


class RegistroForm(EstiloMixin, UserCreationForm):
    """
    UserCreationForm ya valida el nombre de usuario, que las dos contraseñas
    coincidan y que la contraseña sea segura (AUTH_PASSWORD_VALIDATORS).
    Aquí se agregan nombre, apellido, correo y cédula.
    """
    first_name = forms.CharField(label='Nombre', max_length=150)
    last_name = forms.CharField(label='Apellido', max_length=150)
    email = forms.EmailField(label='Correo electrónico')
    cedula = forms.CharField(label='Cédula', max_length=10, validators=[validar_cedula])

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'cedula')
        labels = {'username': 'Nombre de usuario'}

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Ya existe una cuenta con ese correo.')
        return email

    def clean_cedula(self):
        cedula = self.cleaned_data['cedula'].strip()
        if Perfil.objects.filter(cedula=cedula).exists():
            raise forms.ValidationError('Ya existe una cuenta con esa cédula.')
        return cedula
