from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import LoginForm

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(
        authentication_form=LoginForm,
        redirect_authenticated_user=True,
    ), name='login'),
    # En Django 5, cerrar sesión solo acepta POST (el menú usa un formulario).
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('registro/', views.registro, name='registro'),
]
