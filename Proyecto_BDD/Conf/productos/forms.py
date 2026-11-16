import datetime

from django import forms

from .models import Artista, Cancion, Playlist


class BootstrapMixin:
    """
    Agrega las clases de Bootstrap a todos los campos del formulario, para no
    repetir attrs={'class': ...} en cada widget.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, forms.Select):
                clase = 'form-select'
            elif isinstance(widget, forms.CheckboxInput):
                clase = 'form-check-input'
            else:
                clase = 'form-control'
            widget.attrs['class'] = f"{widget.attrs.get('class', '')} {clase}".strip()


# ---------------------------------------------------------------- Artistas

class ArtistaForm(BootstrapMixin, forms.ModelForm):

    class Meta:
        model = Artista
        fields = ['nombre', 'pais']
        labels = {'nombre': 'Nombre', 'pais': 'País'}
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Ej.: Shakira'}),
            'pais': forms.TextInput(attrs={'placeholder': 'Ej.: Colombia'}),
        }

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        # Evita registrar dos veces el mismo artista (sin distinguir mayúsculas).
        repetido = Artista.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            repetido = repetido.exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError('Ya existe un artista con ese nombre.')
        return nombre


# ---------------------------------------------------------------- Canciones

class CancionForm(BootstrapMixin, forms.ModelForm):

    class Meta:
        model = Cancion
        fields = ['titulo', 'artista', 'genero', 'anio',
                  'duracion_segundos', 'popularidad']
        labels = {
            'titulo': 'Título',
            'artista': 'Artista',
            'genero': 'Género',
            'anio': 'Año',
            'duracion_segundos': 'Duración (segundos)',
            'popularidad': 'Popularidad (0-100)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['artista'].queryset = Artista.objects.order_by('nombre')
        self.fields['artista'].empty_label = 'Seleccione un artista'

    def clean_titulo(self):
        return self.cleaned_data['titulo'].strip()

    def clean_anio(self):
        anio = self.cleaned_data.get('anio')
        actual = datetime.date.today().year
        if anio is not None and not (1900 <= anio <= actual):
            raise forms.ValidationError(f'El año debe estar entre 1900 y {actual}.')
        return anio

    def clean_duracion_segundos(self):
        duracion = self.cleaned_data.get('duracion_segundos')
        if duracion is not None and duracion <= 0:
            raise forms.ValidationError('La duración debe ser mayor que 0.')
        return duracion

    def clean_popularidad(self):
        popularidad = self.cleaned_data.get('popularidad')
        if popularidad is not None and not (0 <= popularidad <= 100):
            raise forms.ValidationError('La popularidad debe estar entre 0 y 100.')
        return popularidad

    def clean(self):
        datos = super().clean()
        titulo, artista = datos.get('titulo'), datos.get('artista')
        if titulo and artista:
            repetida = Cancion.objects.filter(titulo__iexact=titulo, artista=artista)
            if self.instance.pk:
                repetida = repetida.exclude(pk=self.instance.pk)
            if repetida.exists():
                raise forms.ValidationError(
                    'Ese artista ya tiene una canción con ese título.'
                )
        return datos


# ---------------------------------------------------------------- Filtro

class FiltroCancionesForm(BootstrapMixin, forms.Form):
    """Filtros del listado de canciones (llegan por GET en la URL)."""

    q = forms.CharField(
        required=False, max_length=100, label='Buscar',
        widget=forms.TextInput(attrs={'placeholder': 'Título o artista', 'type': 'search'})
    )
    genero = forms.ChoiceField(required=False, label='Género')
    anio_desde = forms.IntegerField(required=False, min_value=1900, label='Desde')
    anio_hasta = forms.IntegerField(required=False, min_value=1900, label='Hasta')
    orden = forms.ChoiceField(
        required=False, label='Ordenar por',
        choices=[
            ('titulo', 'Título (A-Z)'),
            ('popularidad', 'Más populares'),
            ('recientes', 'Más recientes'),
        ],
    )

    def __init__(self, *args, generos=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['genero'].choices = [('', 'Todos los géneros')] + [(g, g) for g in generos]
        for nombre in ('anio_desde', 'anio_hasta'):
            self.fields[nombre].widget.attrs['placeholder'] = 'Año'

    def clean_q(self):
        return self.cleaned_data['q'].strip()


# ---------------------------------------------------------------- Playlists

class PlaylistForm(BootstrapMixin, forms.ModelForm):

    class Meta:
        model = Playlist
        fields = ['nombre', 'publica']
        labels = {'nombre': 'Nombre', 'publica': 'Pública'}
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Nombre de la playlist'})
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        # Un mismo usuario no puede tener dos playlists con el mismo nombre
        # (otros usuarios sí pueden usar ese nombre).
        if self.usuario is not None:
            repetida = Playlist.objects.filter(propietario=self.usuario, nombre__iexact=nombre)
            if self.instance.pk:
                repetida = repetida.exclude(pk=self.instance.pk)
            if repetida.exists():
                raise forms.ValidationError('Ya tiene una playlist con ese nombre.')
        return nombre


class AgregarCancionForm(forms.Form):
    """
    Recibe solo el id de la canción elegida en el buscador.

    Antes era un <select> con TODAS las canciones. Ahora el campo es oculto:
    el buscador con autocompletado (JavaScript + /canciones/buscar/) escribe
    el id aquí. ModelChoiceField valida que ese id exista con una sola
    consulta por clave primaria, sin cargar las 200.000 filas.
    """
    cancion = forms.ModelChoiceField(
        queryset=Cancion.objects.all(),
        widget=forms.HiddenInput,
    )
