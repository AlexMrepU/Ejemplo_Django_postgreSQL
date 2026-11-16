from django.conf import settings
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db import models
from django.db.models.functions import Upper
from django.utils import timezone


# Todos los modelos son "managed" (valor por defecto): Django crea y modifica
# sus tablas en PostgreSQL al ejecutar "python manage.py migrate".
# Antes tenían managed = False, que le indica a Django que la tabla ya existe
# y que no debe crearla; por eso las tablas nunca aparecían en la base.


class Artista(models.Model):
    id_artista = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    pais = models.CharField(max_length=60, null=True, blank=True)

    class Meta:
        db_table = 'artistas'
        ordering = ['nombre']
        indexes = [
            # Búsqueda "contiene" (nombre__icontains). Django la traduce a
            #   UPPER(nombre) LIKE UPPER('%texto%')
            # Un índice B-tree no sirve cuando el patrón empieza con %, pero un
            # índice GIN de trigramas (pg_trgm) sí. Se indexa UPPER(nombre)
            # porque esa es exactamente la expresión que aparece en el WHERE.
            GinIndex(OpClass(Upper('nombre'), name='gin_trgm_ops'),
                     name='ix_artista_nombre_trgm'),
            # Ordenar alfabéticamente y paginar (ORDER BY nombre LIMIT 50).
            models.Index(fields=['nombre'], name='ix_artista_nombre'),
        ]

    def __str__(self):
        return self.nombre


class Cancion(models.Model):
    id_cancion = models.AutoField(primary_key=True)
    titulo = models.CharField(max_length=150)
    artista = models.ForeignKey(
        Artista,
        on_delete=models.PROTECT,   # no permite borrar un artista con canciones
        db_column='id_artista',
        related_name='canciones'
    )
    genero = models.CharField(max_length=50, null=True, blank=True)
    anio = models.IntegerField(null=True, blank=True)
    duracion_segundos = models.IntegerField(null=True, blank=True)
    popularidad = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'canciones'
        verbose_name_plural = 'canciones'
        indexes = [
            # Búsqueda por título con comodín inicial (ver Artista).
            GinIndex(OpClass(Upper('titulo'), name='gin_trgm_ops'),
                     name='ix_cancion_titulo_trgm'),
            # Un índice por cada forma de ordenar el listado. Con 200.000
            # filas, ORDER BY ... LIMIT 50 lee solo 50 entradas del índice
            # en lugar de ordenar la tabla completa. id_cancion va al final
            # para desempatar y que la paginación sea estable.
            models.Index(fields=['titulo', 'id_cancion'], name='ix_cancion_titulo'),
            # Los índices para ordenar por popularidad y por año
            # (DESC NULLS LAST) se crean con SQL en la migración 0002: Django
            # 5.2 omite "NULLS LAST" al generar el índice, y si el orden del
            # índice no coincide con el del ORDER BY, PostgreSQL no lo usa.
            # Filtro por género (WHERE genero = 'Rock').
            models.Index(fields=['genero', 'titulo'], name='ix_cancion_genero'),
        ]

    def __str__(self):
        return self.titulo


class Playlist(models.Model):
    id_playlist = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    # Dueño de la playlist. Es null=True solo por las playlists creadas antes
    # de que existiera el login; esas quedan visibles para los administradores.
    propietario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='playlists',
        null=True,
        blank=True,
        db_column='id_usuario'
    )
    publica = models.BooleanField(
        default=False,
        help_text='Si está marcada, otros usuarios pueden verla en "Explorar".'
    )
    creada = models.DateTimeField(default=timezone.now)
    canciones = models.ManyToManyField(
        Cancion,
        through='PlaylistCancion',
        related_name='playlists',
        blank=True
    )

    class Meta:
        db_table = 'playlists'
        indexes = [
            # "Mis playlists": WHERE id_usuario = X ORDER BY nombre
            models.Index(fields=['propietario', 'nombre'], name='ix_playlist_propietario'),
            # "Explorar": índice parcial, solo contiene las filas públicas.
            models.Index(fields=['-creada'], name='ix_playlist_publicas',
                         condition=models.Q(publica=True)),
        ]

    def __str__(self):
        return self.nombre


class PlaylistCancion(models.Model):
    """
    Tabla intermedia playlist <-> canción (relación N:M con atributo
    "posicion"). Antes no existía como modelo, así que Django nunca la
    creaba y las vistas fallaban al insertar o consultar en ella.
    """
    playlist = models.ForeignKey(
        Playlist,
        on_delete=models.CASCADE,   # al borrar una playlist se borran sus filas
        db_column='id_playlist'
    )
    cancion = models.ForeignKey(
        Cancion,
        on_delete=models.CASCADE,
        db_column='id_cancion'
    )
    posicion = models.PositiveIntegerField()

    class Meta:
        db_table = 'playlist_cancion'
        ordering = ['posicion']
        constraints = [
            # Una canción no puede repetirse dentro de la misma playlist.
            models.UniqueConstraint(
                fields=['playlist', 'cancion'],
                name='uq_playlist_cancion'
            ),
        ]
        indexes = [
            # Mostrar la playlist en orden: WHERE id_playlist = X ORDER BY posicion
            models.Index(fields=['playlist', 'posicion'], name='ix_playlist_posicion'),
        ]

    def __str__(self):
        return f'{self.playlist} #{self.posicion}: {self.cancion}'
