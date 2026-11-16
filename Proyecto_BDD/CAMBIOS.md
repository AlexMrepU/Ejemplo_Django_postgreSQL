# Correcciones aplicadas a Proyecto_BDD

## CRUD de artistas, canciones y playlists (nuevo)

| Módulo    | Listar (con búsqueda) | Crear | Editar | Eliminar |
|-----------|-----------------------|-------|--------|----------|
| Artistas  | /artistas/            | /artistas/crear/  | /artistas/<id>/editar/  | /artistas/<id>/eliminar/  |
| Canciones | /canciones/           | /canciones/crear/ | /canciones/<id>/editar/ | /canciones/<id>/eliminar/ |
| Playlists | /playlists/           | (formulario en la lista) | /playlists/<id>/editar/ | /playlists/<id>/eliminar/ |

Dentro de cada playlist (/playlists/<id>/): agregar canción y quitar canción
(POST a /playlists/<id>/quitar/<id_cancion>/), con renumeración automática de posiciones.

Archivos nuevos o modificados:
- `productos/forms.py`: ArtistaForm, CancionForm, PlaylistForm, AgregarCancionForm y un
  mixin que aplica las clases de Bootstrap a todos los campos.
- `productos/views.py`: vistas de los tres CRUD (funciones, igual que el resto del proyecto).
- `productos/urls.py`: rutas nuevas.
- `productos/templates/productos/formulario.html`: plantilla única para crear/editar.
- `productos/templates/productos/confirmar_eliminar.html`: plantilla única de confirmación.
- `productos/templates/productos/artistas.html`: nueva lista de artistas.
- `productos/templatetags/musica.py`: filtro `duracion` (218 -> 3:38).

Reglas de negocio:
- No se permiten artistas con el mismo nombre (sin distinguir mayúsculas).
- No se permiten dos canciones con el mismo título para el mismo artista.
- Año entre 1900 y el año actual; duración mayor que 0; popularidad entre 0 y 100.
- Un artista con canciones no se puede eliminar (on_delete=PROTECT); la pantalla lo avisa.
- Al eliminar una canción se quita de todas las playlists y se renumeran sus posiciones.
- Al eliminar una playlist se borran sus filas de playlist_cancion, no las canciones.
- Las acciones que modifican datos (eliminar, quitar) solo aceptan POST.


## Las tablas no se creaban en PostgreSQL (causa principal)

Los modelos `Artista`, `Cancion` y `Playlist` tenían `managed = False`. Esa opción le dice a
Django "la tabla ya existe, no la crees", por eso `migrate` terminaba sin errores pero en la
base solo aparecía `Main_user`. Además, la tabla intermedia `playlist_cancion` no tenía modelo.

- Se quitó `managed = False`: ahora Django crea y mantiene las tablas.
- Se agregó el modelo `PlaylistCancion` (tabla `playlist_cancion`) con su restricción
  `UNIQUE (id_playlist, id_cancion)`, y `Playlist.canciones` como relación N:M a través de ella.
- `Cancion.artista` usa `on_delete=PROTECT`: no se puede borrar un artista que tenga canciones.
- Las migraciones antiguas de `productos` (0001-0003) se reemplazaron por
  `0001_crear_tablas.py`. Tiene otro nombre a propósito: como Django ya tenía registradas como
  aplicadas las anteriores, una nueva `0001_initial` se habría saltado y las tablas seguirían
  sin crearse.


1. **/playlists/ daba error 500 (TemplateDoesNotExist).**
   La vista renderiza `productos/playlists.html`, pero la plantilla se llamaba `playlist.html`.
   Se renombró la plantilla a `playlists.html`.

2. **Nombre de la tabla de artistas inconsistente.**
   La migración 0002 cambió el modelo `Artista` a la tabla `artista`, pero en PostgreSQL la
   tabla se llama `artistas` (como `canciones` y `playlists`). Se corrigió el modelo y se
   agregó `productos/migrations/0003_alter_artista_table.py`. Ahora el SQL toma el nombre de la tabla del propio
   modelo (`Artista._meta.db_table`), así ORM y SQL no se vuelven a desalinear.

3. **El modelo `Main.User` solo tenía la columna `cargo`.**
   `nombre = models.CharField(...),` con coma final crea una tupla, no un campo, y Django lo ignora.
   Se quitaron las comas y se agregó la migración `Main/migrations/0002_user_nombre_cedula.py`.

## Errores de lógica

4. **Canciones duplicadas en una playlist.** La app esperaba un `IntegrityError` para detectar
   duplicados, pero si `playlist_cancion` no tiene restricción UNIQUE la canción se inserta
   otra vez y se muestra "agregada correctamente". Ahora se verifica con `EXISTS` antes de
   insertar y se bloquea la playlist (`SELECT ... FOR UPDATE`) para que dos peticiones
   simultáneas no obtengan la misma posición.
   Recomendado además en la BD:
   `ALTER TABLE playlist_cancion ADD CONSTRAINT uq_playlist_cancion UNIQUE (id_playlist, id_cancion);`

5. **Formulario de playlist inválido sin aviso.** Si el nombre venía vacío, se redirigía sin
   mensaje. Ahora se muestra el formulario con sus errores.

6. **Mensajes de error sin color.** Django etiqueta `messages.error` como `error`, y Bootstrap
   no tiene `alert-error`. Se agregó `MESSAGE_TAGS` en settings para mapearlo a `danger`.

7. **Vistas POST aceptaban GET.** `crear_playlist` y `agregar_cancion` ahora usan `@require_POST`.

## Mejoras de configuración

- Credenciales de la BD leídas de variables de entorno (`DB_NAME`, `DB_USER`, `DB_PASSWORD`,
  `DB_HOST`, `DB_PORT`), con los valores actuales como respaldo. Antes de publicar el proyecto,
  quitar la contraseña del archivo.
- `LANGUAGE_CODE = 'es-ec'`, `TIME_ZONE = 'America/Guayaquil'`.
- Modelos registrados en el admin de Django.
- `requirements.txt` agregado.
- Eliminados `db.sqlite3` (vacío, no se usa) y las carpetas `__pycache__`.

## Cómo aplicar

    pip install -r requirements.txt
    cd Conf
    python manage.py migrate
    python manage.py runserver

Nota: si la tabla `Main_user` ya tiene más de una fila, la migración 0002 fallará por la
restricción UNIQUE de `cedula`; vaciarla o asignar cédulas distintas antes de migrar.
