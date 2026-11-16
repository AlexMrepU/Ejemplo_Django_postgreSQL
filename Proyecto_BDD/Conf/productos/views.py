from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import connection, transaction, IntegrityError
from django.db.models import Count, F, OuterRef, ProtectedError, Q, Subquery
from django.db.models.functions import Coalesce
from django.http import Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from Main.roles import es_administrador, solo_administrador

from .models import Playlist, Cancion, Artista, PlaylistCancion
from .forms import (
    ArtistaForm, CancionForm, PlaylistForm, AgregarCancionForm, FiltroCancionesForm,
)


# Nombres reales de las tablas, tomados de los modelos. Así el SQL crudo
# nunca se desalinea del ORM.
T_ARTISTA = Artista._meta.db_table
T_CANCION = Cancion._meta.db_table
T_PLAYLIST = Playlist._meta.db_table
T_PLAYLIST_CANCION = PlaylistCancion._meta.db_table


# ===================================================================
# Utilidades
# ===================================================================

def _formulario(request, form, titulo, url_cancelar):
    """Renderiza la plantilla genérica de crear/editar."""
    return render(request, 'productos/formulario.html', {
        'form': form,
        'titulo': titulo,
        'url_cancelar': url_cancelar,
    })


def _confirmar_eliminar(request, objeto, tipo, url_cancelar, avisos=None, bloqueado=False):
    """Renderiza la plantilla genérica de confirmación de borrado."""
    return render(request, 'productos/confirmar_eliminar.html', {
        'objeto': objeto,
        'tipo': tipo,
        'url_cancelar': url_cancelar,
        'avisos': avisos or [],
        'bloqueado': bloqueado,
    })


def _paginar(request, queryset, por_pagina=None):
    """
    Devuelve solo la página pedida (?page=N).

    Con 200.000 canciones no se puede enviar todo al navegador. Paginator
    ejecuta dos consultas pequeñas:
        SELECT COUNT(*) ...            -> total de filas, para los enlaces
        SELECT ... LIMIT 50 OFFSET n   -> solo las filas de esta página
    get_page() corrige valores inválidos (?page=abc o ?page=99999).
    """
    paginator = Paginator(queryset, por_pagina or settings.FILAS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get('page'))
    pagina.rango = paginator.get_elided_page_range(pagina.number, on_each_side=2, on_ends=1)
    return pagina


def obtener_playlist_o_404(request, id_playlist, para_editar=False):
    """
    Carga una playlist verificando permisos:
    - Ver: el dueño, cualquier usuario si es pública, o un administrador.
    - Editar (renombrar, agregar, quitar, reordenar): solo el dueño.
    Si no puede verla responde 404 (no 403), para no revelar que existe.
    """
    playlist = get_object_or_404(
        Playlist.objects.select_related('propietario'), id_playlist=id_playlist
    )
    es_duenio = playlist.propietario_id == request.user.id

    if not (es_duenio or playlist.publica or es_administrador(request.user)):
        raise Http404('Playlist no encontrada.')

    if para_editar and not es_duenio:
        raise PermissionDenied('Solo el dueño puede modificar esta playlist.')

    playlist.es_duenio = es_duenio
    return playlist


def generos_disponibles():
    """
    Lista de géneros para el filtro. SELECT DISTINCT sobre 200.000 filas
    cuesta varias decenas de milisegundos, y la lista casi nunca cambia, así
    que se guarda en caché 10 minutos.
    """
    generos = cache.get('generos')
    if generos is None:
        generos = list(
            Cancion.objects.exclude(genero__isnull=True).exclude(genero='')
            .order_by('genero').values_list('genero', flat=True).distinct()
        )
        cache.set('generos', generos, 600)
    return generos


# ===================================================================
# Inicio
# ===================================================================

@login_required
def inicio(request):

    contexto = {
        'total_artistas': Artista.objects.count(),
        'total_canciones': Cancion.objects.count(),
        'mis_playlists': Playlist.objects.filter(propietario=request.user)
            .annotate(num_canciones=Count('canciones')).order_by('-creada')[:6],
        'total_mis_playlists': Playlist.objects.filter(propietario=request.user).count(),
        'publicas_recientes': Playlist.objects.filter(publica=True)
            .exclude(propietario=request.user)
            .select_related('propietario')
            .annotate(num_canciones=Count('canciones')).order_by('-creada')[:4],
    }

    return render(request, 'productos/inicio.html', contexto)


# ===================================================================
# Artistas: todos pueden consultar, solo el Administrador modifica
# ===================================================================

@login_required
def listar_artistas(request):

    q = request.GET.get('q', '').strip()

    artistas = Artista.objects.order_by('nombre', 'id_artista')

    if q:
        artistas = artistas.filter(Q(nombre__icontains=q) | Q(pais__icontains=q))

    # Número de canciones de cada artista con una subconsulta correlacionada:
    #   (SELECT COUNT(*) FROM canciones c WHERE c.id_artista = artistas.id_artista)
    # Con annotate(Count('canciones')) PostgreSQL agrupaba las 200.000
    # canciones de todos los artistas antes de quedarse con 50. Así solo
    # cuenta las de los 50 artistas de la página, usando el índice de la FK.
    num_canciones = (
        Cancion.objects.filter(artista=OuterRef('pk')).order_by()
        .values('artista').annotate(total=Count('*')).values('total')
    )
    artistas = artistas.annotate(num_canciones=Coalesce(Subquery(num_canciones), 0))

    return render(request, 'productos/artistas.html', {
        'pagina': _paginar(request, artistas),
        'q': q,
    })


@solo_administrador
def crear_artista(request):

    form = ArtistaForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        artista = form.save()
        messages.success(request, f'Artista "{artista}" creado correctamente.')
        return redirect('listar_artistas')

    return _formulario(request, form, 'Nuevo artista', 'listar_artistas')


@solo_administrador
def editar_artista(request, id_artista):

    artista = get_object_or_404(Artista, id_artista=id_artista)
    form = ArtistaForm(request.POST or None, instance=artista)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Artista "{artista}" actualizado.')
        return redirect('listar_artistas')

    return _formulario(request, form, f'Editar artista: {artista}', 'listar_artistas')


@solo_administrador
def eliminar_artista(request, id_artista):

    artista = get_object_or_404(Artista, id_artista=id_artista)
    num_canciones = artista.canciones.count()

    if request.method == 'POST':
        try:
            artista.delete()
            messages.success(request, f'Artista "{artista}" eliminado.')
        except ProtectedError:
            # Cancion.artista usa on_delete=PROTECT: PostgreSQL no permite
            # dejar canciones sin artista.
            messages.error(
                request,
                f'No se puede eliminar "{artista}": tiene {num_canciones} '
                'canción(es) registradas. Elimínelas o asígnelas a otro artista primero.'
            )
        return redirect('listar_artistas')

    avisos = []
    if num_canciones:
        avisos.append(
            f'Este artista tiene {num_canciones} canción(es). '
            'No se puede eliminar mientras las tenga.'
        )

    return _confirmar_eliminar(
        request, artista, 'artista', 'listar_artistas',
        avisos=avisos, bloqueado=bool(num_canciones)
    )


# ===================================================================
# Canciones: todos pueden consultar, solo el Administrador modifica
# ===================================================================

# Cada opción de orden usa un índice creado en la migración 0002.
# id_cancion desempata: sin él, dos canciones con la misma popularidad
# podrían aparecer en dos páginas distintas o en ninguna.
ORDENES = {
    'titulo': [F('titulo').asc(), F('id_cancion').asc()],
    'popularidad': [F('popularidad').desc(nulls_last=True), F('id_cancion').asc()],
    'recientes': [F('anio').desc(nulls_last=True), F('id_cancion').asc()],
}


@login_required
def listar_canciones(request):

    filtro = FiltroCancionesForm(request.GET or None, generos=generos_disponibles())
    canciones = Cancion.objects.select_related('artista')
    orden = 'titulo'

    if filtro.is_valid():
        datos = filtro.cleaned_data
        q = datos.get('q')
        if q:
            # La búsqueda se hace en dos consultas que sí usan índice:
            # títulos (índice GIN de trigramas) y artistas (otro índice GIN).
            # Un solo WHERE con "titulo ILIKE ... OR artista.nombre ILIKE ..."
            # mezcla dos tablas y obliga a PostgreSQL a recorrer las 200.000
            # filas (Seq Scan).
            ids_artistas = list(
                Artista.objects.filter(nombre__icontains=q)
                .values_list('id_artista', flat=True)[:500]
            )
            canciones = canciones.filter(
                Q(titulo__icontains=q) | Q(artista_id__in=ids_artistas)
            )
        if datos.get('genero'):
            canciones = canciones.filter(genero=datos['genero'])
        if datos.get('anio_desde'):
            canciones = canciones.filter(anio__gte=datos['anio_desde'])
        if datos.get('anio_hasta'):
            canciones = canciones.filter(anio__lte=datos['anio_hasta'])
        orden = datos.get('orden') or 'titulo'

    canciones = canciones.order_by(*ORDENES[orden])

    return render(request, 'productos/canciones.html', {
        'pagina': _paginar(request, canciones),
        'filtro': filtro,
        'hay_filtros': filtro.is_bound and any(
            request.GET.get(k) for k in ('q', 'genero', 'anio_desde', 'anio_hasta')
        ),
        'hay_artistas': Artista.objects.exists(),
    })


@login_required
@require_GET
def buscar_canciones(request):
    """
    Autocompletado (devuelve JSON) para el buscador de "Agregar canción".

    Reemplaza al <select> con todas las canciones: con 200.000 filas ese
    desplegable pesaba varios MB y tardaba segundos en cargar. Ahora el
    navegador pide solo las 20 coincidencias del texto escrito.
    Ej.: /canciones/buscar/?q=amor&playlist=3
    """
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'resultados': []})

    canciones = (
        Cancion.objects.select_related('artista')
        .filter(titulo__icontains=q)
        .order_by(F('popularidad').desc(nulls_last=True), 'id_cancion')
    )

    id_playlist = request.GET.get('playlist', '')
    if id_playlist.isdigit():
        # No sugerir canciones que ya están en la playlist.
        canciones = canciones.exclude(playlists__id_playlist=int(id_playlist))

    resultados = [
        {
            'id': c.id_cancion,
            'titulo': c.titulo,
            'artista': c.artista.nombre,
            'anio': c.anio,
        }
        for c in canciones[:20]
    ]
    return JsonResponse({'resultados': resultados})


@solo_administrador
def crear_cancion(request):

    if not Artista.objects.exists():
        messages.warning(request, 'Primero registre al menos un artista.')
        return redirect('crear_artista')

    # Permite llegar desde la lista de artistas con el artista ya elegido:
    # /canciones/crear/?artista=3
    inicial = {}
    if request.GET.get('artista', '').isdigit():
        inicial['artista'] = request.GET['artista']

    form = CancionForm(request.POST or None, initial=inicial)

    if request.method == 'POST' and form.is_valid():
        cancion = form.save()
        cache.delete('generos')  # puede haber un género nuevo
        messages.success(request, f'Canción "{cancion}" creada correctamente.')
        return redirect('listar_canciones')

    return _formulario(request, form, 'Nueva canción', 'listar_canciones')


@solo_administrador
def editar_cancion(request, id_cancion):

    cancion = get_object_or_404(Cancion, id_cancion=id_cancion)
    form = CancionForm(request.POST or None, instance=cancion)

    if request.method == 'POST' and form.is_valid():
        form.save()
        cache.delete('generos')
        messages.success(request, f'Canción "{cancion}" actualizada.')
        return redirect('listar_canciones')

    return _formulario(request, form, f'Editar canción: {cancion}', 'listar_canciones')


@solo_administrador
def eliminar_cancion(request, id_cancion):

    cancion = get_object_or_404(Cancion, id_cancion=id_cancion)

    if request.method == 'POST':
        with transaction.atomic():
            # Al borrar la canción, PostgreSQL borra en cascada sus filas de
            # playlist_cancion. Luego se renumeran las posiciones de cada
            # playlist afectada para que no queden huecos (1, 2, 4...).
            afectadas = list(
                PlaylistCancion.objects.filter(cancion=cancion)
                .values_list('playlist_id', 'posicion')
            )
            cancion.delete()
            for id_playlist, posicion in afectadas:
                PlaylistCancion.objects.filter(
                    playlist_id=id_playlist, posicion__gt=posicion
                ).update(posicion=F('posicion') - 1)

        messages.success(request, f'Canción "{cancion}" eliminada.')
        return redirect('listar_canciones')

    avisos = []
    num_playlists = cancion.playlists.count()
    if num_playlists:
        avisos.append(
            f'La canción está en {num_playlists} playlist(s); '
            'también se quitará de ellas.'
        )

    return _confirmar_eliminar(request, cancion, 'canción', 'listar_canciones', avisos=avisos)


# ===================================================================
# Playlists: cada usuario gestiona las suyas
# ===================================================================

@login_required
def listar_playlists(request, form=None):

    playlists = (
        Playlist.objects.filter(propietario=request.user)
        .annotate(num_canciones=Count('canciones'))
        .order_by('nombre', 'id_playlist')
    )

    contexto = {
        'pagina': _paginar(request, playlists, por_pagina=24),
        'form': form or PlaylistForm(usuario=request.user),
    }

    # Playlists antiguas (creadas antes del login) que quedaron sin dueño.
    if es_administrador(request.user):
        contexto['sin_duenio'] = (
            Playlist.objects.filter(propietario__isnull=True)
            .annotate(num_canciones=Count('canciones')).order_by('nombre')
        )

    return render(request, 'productos/playlists.html', contexto)


@login_required
def explorar_playlists(request):
    """Playlists públicas de otros usuarios."""

    q = request.GET.get('q', '').strip()

    playlists = (
        Playlist.objects.filter(publica=True)
        .exclude(propietario=request.user)
        .select_related('propietario')
        .annotate(num_canciones=Count('canciones'))
        .order_by('-creada', 'id_playlist')
    )
    if q:
        playlists = playlists.filter(nombre__icontains=q)

    return render(request, 'productos/explorar.html', {
        'pagina': _paginar(request, playlists, por_pagina=24),
        'q': q,
    })


@login_required
@require_POST
def crear_playlist(request):

    form = PlaylistForm(request.POST, usuario=request.user)

    if form.is_valid():
        playlist = form.save(commit=False)
        playlist.propietario = request.user  # el dueño es siempre quien la crea
        playlist.save()
        messages.success(request, f'Playlist "{playlist}" creada correctamente.')
        return redirect('detalle_playlist', id_playlist=playlist.id_playlist)

    # Si el formulario es inválido se vuelve a mostrar con sus errores.
    messages.error(request, 'Revise los datos de la playlist.')
    return listar_playlists(request, form=form)


@login_required
def editar_playlist(request, id_playlist):

    playlist = obtener_playlist_o_404(request, id_playlist, para_editar=True)
    form = PlaylistForm(request.POST or None, instance=playlist, usuario=request.user)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Playlist "{playlist}" actualizada.')
        return redirect('detalle_playlist', id_playlist=id_playlist)

    return _formulario(request, form, f'Editar playlist: {playlist}', 'listar_playlists')


@login_required
def eliminar_playlist(request, id_playlist):

    # El dueño puede eliminarla; un administrador también (moderación).
    playlist = obtener_playlist_o_404(request, id_playlist)
    if not (playlist.es_duenio or es_administrador(request.user)):
        raise PermissionDenied('Solo el dueño puede eliminar esta playlist.')

    if request.method == 'POST':
        # on_delete=CASCADE en PlaylistCancion: se borran también sus filas
        # de playlist_cancion (las canciones en sí no se borran).
        playlist.delete()
        messages.success(request, f'Playlist "{playlist}" eliminada.')
        return redirect('listar_playlists')

    avisos = []
    num = playlist.canciones.count()
    if num:
        avisos.append(
            f'La playlist tiene {num} canción(es). Solo se quitarán de la '
            'playlist; las canciones seguirán existiendo.'
        )

    return _confirmar_eliminar(request, playlist, 'playlist', 'listar_playlists', avisos=avisos)


@login_required
def detalle_playlist(request, id_playlist):

    playlist = obtener_playlist_o_404(request, id_playlist)

    with connection.cursor() as cursor:

        cursor.execute(f"""
            SELECT
                c.id_cancion,
                c.titulo,
                a.nombre AS artista,
                c.genero,
                c.duracion_segundos,
                pc.posicion
            FROM {T_PLAYLIST_CANCION} pc
            INNER JOIN {T_CANCION} c
                ON pc.id_cancion = c.id_cancion
            INNER JOIN {T_ARTISTA} a
                ON c.id_artista = a.id_artista
            WHERE pc.id_playlist = %s
            ORDER BY pc.posicion;
        """, [id_playlist])

        columnas = [col[0] for col in cursor.description]

        canciones = [
            dict(zip(columnas, fila))
            for fila in cursor.fetchall()
        ]

    duracion_total = sum(c['duracion_segundos'] or 0 for c in canciones)

    contexto = {
        'playlist': playlist,
        'canciones': canciones,
        'duracion_total': duracion_total,
        'puede_eliminar': playlist.es_duenio or es_administrador(request.user),
    }

    return render(request, 'productos/detalle_playlist.html', contexto)


@login_required
@require_POST
def agregar_cancion(request, id_playlist):

    obtener_playlist_o_404(request, id_playlist, para_editar=True)

    form = AgregarCancionForm(request.POST)

    if not form.is_valid():
        messages.error(request, 'Busque y seleccione una canción de la lista.')
        return redirect('detalle_playlist', id_playlist=id_playlist)

    cancion = form.cleaned_data['cancion']
    id_cancion = cancion.id_cancion

    try:

        with transaction.atomic():

            with connection.cursor() as cursor:

                # Bloquea la fila de la playlist mientras se calcula la
                # posición: evita que dos peticiones simultáneas obtengan
                # el mismo MAX(posicion) + 1.
                cursor.execute(
                    f"SELECT 1 FROM {T_PLAYLIST} WHERE id_playlist = %s FOR UPDATE;",
                    [id_playlist]
                )

                cursor.execute(f"""
                    SELECT EXISTS (
                        SELECT 1 FROM {T_PLAYLIST_CANCION}
                        WHERE id_playlist = %s AND id_cancion = %s
                    );
                """, [id_playlist, id_cancion])

                if cursor.fetchone()[0]:
                    messages.warning(
                        request,
                        'La canción ya existe en esta playlist.'
                    )
                    return redirect('detalle_playlist', id_playlist=id_playlist)

                cursor.execute(f"""
                    SELECT COALESCE(MAX(posicion), 0) + 1
                    FROM {T_PLAYLIST_CANCION}
                    WHERE id_playlist = %s;
                """, [id_playlist])

                posicion = cursor.fetchone()[0]

                cursor.execute(f"""
                    INSERT INTO {T_PLAYLIST_CANCION}
                    (id_playlist, id_cancion, posicion)
                    VALUES (%s, %s, %s);
                """, [id_playlist, id_cancion, posicion])

        messages.success(request, f'"{cancion.titulo}" agregada a la playlist.')

    except IntegrityError:
        # Respaldo: la restricción UNIQUE (id_playlist, id_cancion) de la BD.
        messages.error(
            request,
            'No se pudo agregar: la canción ya existe en esta playlist.'
        )

    return redirect('detalle_playlist', id_playlist=id_playlist)


@login_required
@require_POST
def quitar_cancion(request, id_playlist, id_cancion):

    obtener_playlist_o_404(request, id_playlist, para_editar=True)

    with transaction.atomic():

        with connection.cursor() as cursor:

            cursor.execute(
                f"SELECT 1 FROM {T_PLAYLIST} WHERE id_playlist = %s FOR UPDATE;",
                [id_playlist]
            )

            # DELETE ... RETURNING devuelve la posición que tenía la canción,
            # para recorrer una posición hacia arriba las que estaban debajo.
            cursor.execute(f"""
                DELETE FROM {T_PLAYLIST_CANCION}
                WHERE id_playlist = %s AND id_cancion = %s
                RETURNING posicion;
            """, [id_playlist, id_cancion])

            fila = cursor.fetchone()

            if fila is None:
                messages.warning(request, 'Esa canción no estaba en la playlist.')
                return redirect('detalle_playlist', id_playlist=id_playlist)

            cursor.execute(f"""
                UPDATE {T_PLAYLIST_CANCION}
                SET posicion = posicion - 1
                WHERE id_playlist = %s AND posicion > %s;
            """, [id_playlist, fila[0]])

    messages.success(request, 'Canción quitada de la playlist.')
    return redirect('detalle_playlist', id_playlist=id_playlist)


@login_required
@require_POST
def mover_cancion(request, id_playlist, id_cancion, direccion):
    """
    Sube o baja una canción una posición, intercambiándola con su vecina.

    Ej.: subir la canción de la posición 4
        antes:  3 = B,  4 = A
        después: 3 = A,  4 = B
    Las dos actualizaciones van en una transacción con la playlist bloqueada
    (FOR UPDATE): si dos personas reordenan a la vez, la segunda espera.
    """
    if direccion not in ('subir', 'bajar'):
        raise Http404('Dirección no válida.')
    obtener_playlist_o_404(request, id_playlist, para_editar=True)
    desplazamiento = -1 if direccion == 'subir' else 1

    with transaction.atomic():

        with connection.cursor() as cursor:

            cursor.execute(
                f"SELECT 1 FROM {T_PLAYLIST} WHERE id_playlist = %s FOR UPDATE;",
                [id_playlist]
            )

            cursor.execute(f"""
                SELECT posicion FROM {T_PLAYLIST_CANCION}
                WHERE id_playlist = %s AND id_cancion = %s;
            """, [id_playlist, id_cancion])
            fila = cursor.fetchone()

            if fila is None:
                messages.warning(request, 'Esa canción no está en la playlist.')
                return redirect('detalle_playlist', id_playlist=id_playlist)

            actual = fila[0]
            destino = actual + desplazamiento

            # Un solo UPDATE intercambia las dos posiciones con CASE.
            # Si la canción ya está primera (o última) no hay vecina y
            # no se modifica ninguna fila.
            cursor.execute(f"""
                UPDATE {T_PLAYLIST_CANCION}
                SET posicion = CASE posicion WHEN %s THEN %s ELSE %s END
                WHERE id_playlist = %s
                  AND posicion IN (%s, %s)
                  AND EXISTS (
                      SELECT 1 FROM {T_PLAYLIST_CANCION}
                      WHERE id_playlist = %s AND posicion = %s
                  );
            """, [actual, destino, actual, id_playlist, actual, destino,
                  id_playlist, destino])

    # Vuelve a la misma fila de la tabla (ancla #c<id>).
    return redirect(reverse('detalle_playlist', args=[id_playlist]) + f'#c{id_cancion}')
