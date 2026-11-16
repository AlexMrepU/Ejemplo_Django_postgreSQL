"""
Compara el plan de ejecución (EXPLAIN ANALYZE) de las consultas reales de la
aplicación CON y SIN los índices creados en la migración 0002.

Uso:
    python manage.py comparar_indices             # tabla resumen
    python manage.py comparar_indices --planes    # además, los planes completos

Cómo funciona "sin índices":
    En PostgreSQL, DROP INDEX se puede deshacer si está dentro de una
    transacción. El comando abre una transacción, borra los índices, ejecuta
    EXPLAIN ANALYZE y hace ROLLBACK: los índices vuelven a existir como si
    nada. Mientras tanto la tabla queda bloqueada, así que ejecútelo solo en
    su base de desarrollo.

Las consultas son las mismas que ejecutan las vistas (se construyen con el
ORM de Django), por eso el resultado refleja lo que pasa en la página.
"""
import re

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.models import F, Q

from productos.models import Artista, Cancion
from productos.views import ORDENES

INDICES = [
    'ix_cancion_titulo_trgm', 'ix_cancion_titulo', 'ix_cancion_popularidad',
    'ix_cancion_anio', 'ix_cancion_genero', 'ix_artista_nombre_trgm', 'ix_artista_nombre',
]


def consultas():
    """(descripción, queryset) de cada caso que se compara."""
    canciones = Cancion.objects.select_related('artista')
    ids_artistas = list(
        Artista.objects.filter(nombre__icontains='volc').values_list('id_artista', flat=True)
    )
    busqueda = canciones.filter(Q(titulo__icontains='luna') | Q(artista_id__in=ids_artistas))

    return [
        ('Página 1, orden por título',
         canciones.order_by(*ORDENES['titulo'])[:50]),
        ('Página 2.000 (OFFSET 99.950)',
         canciones.order_by(*ORDENES['titulo'])[99_950:100_000]),
        ('Más populares, página 1',
         canciones.order_by(*ORDENES['popularidad'])[:50]),
        ('Más recientes, página 1',
         canciones.order_by(*ORDENES['recientes'])[:50]),
        ('Filtro género = Pasillo',
         canciones.filter(genero='Pasillo').order_by(*ORDENES['titulo'])[:50]),
        ('Buscar "luna" (título o artista)',
         busqueda.order_by(*ORDENES['titulo'])[:50]),
        ('COUNT(*) de la búsqueda "luna"',
         Cancion.objects.filter(Q(titulo__icontains='luna') | Q(artista_id__in=ids_artistas))),
        ('Autocompletado "madrugada"',
         canciones.filter(titulo__icontains='madrugada')
         .order_by(F('popularidad').desc(nulls_last=True), 'id_cancion')[:20]),
        ('Buscar artista "volc"',
         Artista.objects.filter(nombre__icontains='volc').order_by('nombre')[:50]),
    ]


def resumir(plan):
    """Extrae del texto de EXPLAIN el tiempo y el tipo de lectura principal."""
    tiempo = float(re.search(r'Execution Time: ([\d.]+) ms', plan).group(1))
    if 'Seq Scan on canciones' in plan or 'Seq Scan on artistas' in plan:
        acceso = 'Seq Scan (lee toda la tabla)'
    else:
        # "Index Scan using ix_x on tabla" o "Bitmap Index Scan on ix_x"
        usados = re.findall(r'Index (?:Only )?Scan (?:Backward )?using (\w+)', plan)
        usados += re.findall(r'Bitmap Index Scan on (\w+)', plan)
        usados = [i for i in dict.fromkeys(usados) if i != 'artistas_pkey']
        acceso = 'Índice: ' + ', '.join(usados) if usados else 'Otro'
    return tiempo, acceso


class Command(BaseCommand):
    help = 'Compara EXPLAIN ANALYZE de las consultas de la app con y sin índices.'

    def add_arguments(self, parser):
        parser.add_argument('--planes', action='store_true', help='Muestra los planes completos.')

    def explicar(self, queryset):
        # Se ejecuta dos veces y se toma la segunda: la primera puede ser más
        # lenta porque los datos aún no están en la memoria caché.
        queryset.explain(analyze=True)
        return queryset.explain(analyze=True, buffers=True)

    def handle(self, *args, **opciones):
        total = Cancion.objects.count()
        self.stdout.write(f'Tabla canciones: {total:,} filas\n'.replace(',', '.'))
        if total < 10_000:
            self.stdout.write(self.style.WARNING(
                'Con pocas filas PostgreSQL prefiere Seq Scan aunque haya índices. '
                'Ejecute primero: python manage.py generar_datos'
            ))

        casos = consultas()

        # 1) Con índices
        con = [self.explicar(qs) for _, qs in casos]

        # 2) Sin índices: DROP INDEX dentro de una transacción + ROLLBACK
        sin = []
        with transaction.atomic():
            with connection.cursor() as cursor:
                for indice in INDICES:
                    cursor.execute(f'DROP INDEX IF EXISTS {indice};')
            sin = [self.explicar(qs) for _, qs in casos]
            transaction.set_rollback(True)   # deshace los DROP INDEX

        # Resumen
        ancho = max(len(d) for d, _ in casos)
        self.stdout.write(f"{'Consulta':<{ancho}}  {'Sin índice':>11}  {'Con índice':>11}  {'Mejora':>7}")
        self.stdout.write('-' * (ancho + 36))
        for (descripcion, _), plan_sin, plan_con in zip(casos, sin, con):
            t_sin, acceso_sin = resumir(plan_sin)
            t_con, acceso_con = resumir(plan_con)
            veces = t_sin / t_con if t_con else 0
            self.stdout.write(
                f'{descripcion:<{ancho}}  {t_sin:>8.2f} ms  {t_con:>8.2f} ms  {veces:>6.1f}x'
            )
            self.stdout.write(self.style.HTTP_INFO(f"{'':<{ancho}}    sin: {acceso_sin}"))
            self.stdout.write(self.style.SUCCESS(f"{'':<{ancho}}    con: {acceso_con}"))

            if opciones['planes']:
                self.stdout.write('\n  --- Plan SIN índices ---\n' + plan_sin)
                self.stdout.write('\n  --- Plan CON índices ---\n' + plan_con + '\n')

        self.stdout.write(
            '\nNota: la página 2.000 sigue siendo más lenta que la 1 aun con índice, '
            'porque OFFSET obliga a recorrer y descartar las 99.950 filas anteriores.'
        )
