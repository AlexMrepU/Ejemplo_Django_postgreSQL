# Guía de mejoras: login por roles, 200.000 canciones y más

Este documento explica qué se cambió, **cómo ponerlo en marcha** y **por qué** se hizo así.
El historial de correcciones anteriores sigue en `CAMBIOS.md`.

---

## 1. Puesta en marcha (en orden)

### 1.1 Instalar dependencias

    pip install -r requirements.txt

Por qué: se agregó `python-dotenv`, que lee el archivo `.env` con las contraseñas.

### 1.2 Revisar el archivo `.env`

El archivo `Conf/.env` (junto a `manage.py`) ya trae sus datos de conexión actuales y una
`SECRET_KEY` nueva. Si cambia de equipo, copie `Conf/.env.example` como `Conf/.env` y complételo.

Por qué: antes la contraseña de PostgreSQL y la `SECRET_KEY` estaban escritas en `settings.py`.
Si el proyecto se sube a GitHub, cualquiera las vería. Ahora `settings.py` las lee del entorno,
y `.gitignore` impide que `.env` se suba. Si falta una variable, Django se detiene con un mensaje
que dice cuál falta.

### 1.3 Respaldar `Main_user` (solo si tiene datos que le importen)

    pg_dump -U postgres -d BDD_PBDD -t '"Main_user"' > respaldo_main_user.sql

Por qué: la migración `Main/0003` elimina esa tabla (ver sección 2.3).

### 1.4 Aplicar las migraciones

    cd Conf
    python manage.py migrate

Esto hace cuatro cosas: activa la extensión `pg_trgm`, crea la tabla `perfiles` y los grupos
**Administrador** y **Usuario**, agrega `propietario`, `publica` y `creada` a `playlists`, y crea
los índices.

### 1.5 Crear el primer administrador

    python manage.py createsuperuser

Por qué: un superusuario siempre se trata como Administrador. Si ya existían playlists, la
migración no pudo asignarles dueño (aún no había usuarios). Aparecen en "Mis playlists",
en la sección "Playlists sin dueño", y como administrador puede verlas o eliminarlas.

### 1.6 Generar 200.000 canciones de prueba

    python manage.py generar_datos              # agrega 3.000 artistas y 200.000 canciones
    python manage.py generar_datos --reemplazar # BORRA el catálogo actual antes de generar

Tarda unos 6 segundos. Use `--reemplazar` solo en su base de pruebas: vacía artistas,
canciones y el contenido de las playlists.

### 1.7 Medir el efecto de los índices

    python manage.py comparar_indices
    python manage.py comparar_indices --planes   # muestra los EXPLAIN completos

### 1.8 Ejecutar

    python manage.py runserver

Entre a http://127.0.0.1:8000/. Sin sesión iniciada, la aplicación lo envía al login.

---

## 2. Login por tipo de usuario

### 2.1 Qué puede hacer cada rol

| Acción | Usuario | Administrador |
|---|---|---|
| Ver catálogo de canciones y artistas (buscar, filtrar) | Sí | Sí |
| Crear, editar o eliminar canciones y artistas | No (error 403) | Sí |
| Crear playlists propias, agregar, quitar y reordenar canciones | Sí | Sí |
| Ver una playlist privada de otra persona | No (error 404) | Sí |
| Ver playlists públicas de otros (Explorar) | Sí | Sí |
| Eliminar una playlist ajena | No | Sí (moderación) |
| Entrar a /admin/ (usuarios y roles) | No | Solo si es staff |

### 2.2 Cómo se asignan los roles

- **Registro público** (`/cuentas/registro/`): pide nombre, apellido, cédula, correo, usuario
  y contraseña. Toda cuenta nueva entra al grupo **Usuario**.
- **Ascender a Administrador**: en `/admin/`, abra **Usuarios**, edite la persona y agréguela
  al grupo **Administrador**.

Por qué así: si el formulario de registro dejara elegir el rol, cualquiera podría registrarse
como administrador. El rol que da permisos lo asigna solo alguien que ya los tiene.

### 2.3 Por qué se reemplazó `Main.User`

`Main.User` (nombre, cédula, cargo) era un modelo independiente: no tenía contraseña ni sesión,
y Django no lo reconoce para iniciar sesión. Se usa el usuario de Django (`auth.User`), que ya
trae contraseñas cifradas, sesiones, login y logout. Lo que le faltaba, la cédula, se guarda
en el nuevo modelo `Main.Perfil` (tabla `perfiles`), unido al usuario con `OneToOneField`.
La cédula se valida con el algoritmo módulo 10 (`Main/validators.py`).

### 2.4 Archivos clave

| Archivo | Qué hace |
|---|---|
| `Main/roles.py` | `es_administrador(user)` y el decorador `@solo_administrador` |
| `Main/context_processors.py` | Pone `es_admin` en todas las plantillas (botones según el rol) |
| `Main/views.py`, `Main/forms.py`, `Main/urls.py` | Login, logout y registro |
| `Main/templates/registration/` | Pantallas de login y registro |
| `Main/templates/403.html` | Página "No tiene permiso" |

Por qué un decorador: cada vista del CRUD del catálogo lleva `@solo_administrador` en una línea.
Esconder el botón en la plantilla no basta, porque alguien puede escribir la URL a mano. La
vista es la que debe rechazar la petición.

Por qué 404 y no 403 en playlists privadas: un 403 confirmaría que la playlist existe.
Con 404, quien no tiene permiso no puede saber qué playlists hay.

---

## 3. Mostrar 200.000 canciones

### 3.1 El problema

1. `/canciones/` enviaba las 200.000 filas en una sola página (varios MB de HTML).
2. En cada playlist, "Agregar canción" era un `<select>` con **todas** las canciones:
   200.000 `<option>` cada vez que se abría una playlist.
3. La búsqueda `icontains` se traduce a `UPPER(titulo) LIKE UPPER('%luna%')`. Un índice B-tree
   no sirve si el patrón empieza con `%`, así que PostgreSQL leía la tabla entera (Seq Scan).

### 3.2 Las soluciones

**Paginación** (`_paginar()` en `productos/views.py`, plantilla `_paginacion.html`).
`Paginator` ejecuta `COUNT(*)` y `SELECT ... LIMIT 50 OFFSET n`. El navegador recibe unos 24 KB
en lugar de varios MB. La etiqueta `{% url_pagina %}` conserva la búsqueda y los filtros al
cambiar de página.

**Índices** (`productos/models.py` y migración `0002`):

| Índice | Para qué consulta |
|---|---|
| `ix_cancion_titulo_trgm` (GIN, `pg_trgm`, sobre `UPPER(titulo)`) | Buscar texto dentro del título |
| `ix_artista_nombre_trgm` (GIN) | Buscar texto dentro del nombre del artista |
| `ix_cancion_titulo (titulo, id_cancion)` | Ordenar A-Z y paginar |
| `ix_cancion_popularidad (popularidad DESC NULLS LAST, id_cancion)` | Orden "Más populares" |
| `ix_cancion_anio (anio DESC NULLS LAST, id_cancion)` | Orden "Más recientes" |
| `ix_cancion_genero (genero, titulo)` | Filtrar por género |
| `ix_playlist_publicas` (índice parcial, solo `publica = true`) | Pantalla Explorar |

Detalles que conviene entender:

- **Por qué `UPPER(titulo)` y no `titulo`**: el índice tiene que contener la misma expresión
  que aparece en el `WHERE`. Django escribe `UPPER(titulo)`, así que se indexa eso.
- **Por qué `id_cancion` al final**: desempata. Sin él, dos canciones con la misma popularidad
  pueden aparecer en dos páginas o en ninguna.
- **Por qué dos índices están en SQL (`RunSQL`)**: Django 5.2 omite `NULLS LAST` al crear el
  índice. Si el orden del índice no coincide con el del `ORDER BY`, PostgreSQL no lo usa.
- **Por qué la búsqueda de artistas va aparte**: un solo `WHERE titulo ILIKE ... OR
  artista.nombre ILIKE ...` mezcla dos tablas y provoca un Seq Scan. Primero se buscan los
  artistas (índice GIN) y luego `titulo ILIKE ... OR id_artista IN (...)`. PostgreSQL combina
  los dos índices con un `BitmapOr`.

**Autocompletado** (`buscar_canciones` en `views.py` y `static/productos/js/autocompletar.js`).
El `<select>` se reemplazó por un campo de texto. Al escribir 2 o más letras, y tras 250 ms sin
teclear, el navegador pide `/canciones/buscar/?q=...` y recibe como máximo 20 coincidencias en
JSON. Excluye las canciones que ya están en la playlist. Se maneja con el teclado (flechas,
Enter y Esc).

**Conteo por artista** (`listar_artistas`). Antes se usaba `annotate(Count('canciones'))`, que
agrupaba las 200.000 canciones para mostrar 50 artistas (unos 107 ms). Ahora una subconsulta
cuenta solo las canciones de los 50 artistas de la página (unos 12 ms).

**Caché de géneros**. `SELECT DISTINCT genero` sobre 200.000 filas se guarda 10 minutos en
memoria y se borra al crear o editar una canción.

### 3.3 Resultados medidos (200.000 canciones, `comparar_indices`)

| Consulta | Sin índice | Con índice |
|---|---|---|
| Página 1, orden por título | 62 ms | 0,18 ms |
| Más populares | 67 ms | 0,17 ms |
| Filtro por género | 14 ms | 0,18 ms |
| Buscar "luna" (título o artista) | 52 ms | 1,5 ms |
| Autocompletado | 45 ms | 0,4 ms |
| Página 2.000 (OFFSET 99.950) | 287 ms | 89 ms |

La última fila es una lección en sí misma: aun con índice, `OFFSET 99950` obliga a recorrer y
descartar 99.950 filas. La alternativa es la paginación por cursor (*keyset*:
`WHERE (titulo, id) > (último_titulo, último_id) LIMIT 50`), que no permite saltar a la página N
pero mantiene el mismo tiempo en cualquier página.

---

## 4. Otras mejoras

### 4.1 Playlists públicas o privadas

Cada playlist tiene la casilla **Pública** (al crearla o en "Editar"). Las públicas aparecen en
**Explorar** y en el inicio de los demás usuarios, que pueden verlas pero no modificarlas.
Un mismo usuario no puede tener dos playlists con el mismo nombre; usuarios distintos sí.

### 4.2 Reordenar canciones

Botones subir y bajar en cada fila (`mover_cancion` en `views.py`). Un solo `UPDATE` con `CASE`
intercambia las dos posiciones dentro de una transacción con `SELECT ... FOR UPDATE`, igual que
agregar y quitar, para que dos peticiones simultáneas no dejen posiciones repetidas.
Después de mover, la página vuelve a la misma fila y la resalta.

### 4.3 Filtros y orden del catálogo

`FiltroCancionesForm` (en `forms.py`) valida los parámetros de la URL: texto, género, rango de
años y orden (título, más populares, más recientes). Como es un formulario de Django, un valor
inválido como `?anio_desde=abc` no rompe la página. Solo se muestra un aviso.

### 4.4 Rediseño visual

- `static/productos/css/app.css`: tema propio sobre Bootstrap. Usa barra lateral color petróleo,
  acento ámbar y las fuentes Bricolage Grotesque (títulos) y Figtree (texto).
- **Portadas generadas**: cada playlist tiene un mosaico de colores calculado desde su `id`
  (filtro `portada` en `templatetags/musica.py`). No hace falta subir imágenes.
- Las cifras usan separador de miles con punto (`200.000`) mediante el filtro `miles`.
- En celulares, el menú lateral pasa a una barra superior.
- Bootstrap y las fuentes se cargan desde CDN, así que la primera vez se necesita internet.

---

## 5. Archivos nuevos o modificados

    requirements.txt                       + python-dotenv
    .gitignore                             nuevo
    Conf/.env, Conf/.env.example           nuevos
    Conf/Conf/settings.py                  .env, login, caché, django.contrib.postgres
    Conf/Conf/urls.py                      + /cuentas/
    Conf/Main/                             roles, perfil, registro, login, admin de usuarios
      migrations/0003_perfil_y_roles.py
    Conf/productos/models.py               propietario, publica, creada, índices
    Conf/productos/migrations/0002_propietario_publica_indices.py
    Conf/productos/views.py                permisos, paginación, filtros, autocompletado, mover
    Conf/productos/forms.py                FiltroCancionesForm, PlaylistForm, AgregarCancionForm
    Conf/productos/urls.py                 + buscar, explorar, mover
    Conf/productos/admin.py                propietario y autocompletado
    Conf/productos/templatetags/musica.py  + url_pagina, portada, miles
    Conf/productos/management/commands/    generar_datos.py, comparar_indices.py
    Conf/productos/static/productos/       css/app.css, js/autocompletar.js
    Conf/productos/templates/productos/    todas rediseñadas; nuevas: explorar,
                                           _paginacion, _tarjeta_playlist

## 6. Ideas para continuar

- Paginación por cursor en el catálogo, para que la página 4.000 sea tan rápida como la 1.
- Carga masiva de canciones desde CSV para el Administrador (`COPY` de PostgreSQL).
- Pruebas automáticas de permisos por rol (`tests.py` sigue vacío).
