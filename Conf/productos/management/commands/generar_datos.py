"""
Genera datos de prueba directamente en PostgreSQL.

Uso:
    python manage.py generar_datos                      # 200.000 canciones, 3.000 artistas
    python manage.py generar_datos --canciones 500000
    python manage.py generar_datos --reemplazar         # borra el catálogo antes

Por qué con SQL y no con el ORM:
    Crear 200.000 objetos con Cancion.objects.create() serían 200.000 INSERT
    (varios minutos). Con INSERT ... SELECT ... FROM generate_series(1, N)
    PostgreSQL genera todas las filas en una sola sentencia, en segundos.
"""
import time

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from productos.models import Artista, Cancion, PlaylistCancion

PREFIJOS = [
    'Los', 'Las', 'La', 'El', 'Grupo', 'Banda', 'Orquesta', 'Dúo', 'Trío', 'Coro',
    'Sonora', 'Combo', 'Ensamble', 'Colectivo', 'Proyecto', 'Hermanos', 'Clan', 'Tribu',
    'Club', 'Sistema', 'Círculo', 'Señal', 'Frente', 'Escuadrón', 'Cuarteto',
    'Taller', 'Unión', 'Estación', 'Nación', 'Familia',
]
NUCLEOS = [
    'Andinos', 'del Sur', 'Eléctricos', 'del Volcán', 'Nocturnos', 'del Puerto',
    'Cósmicos', 'de Neón', 'Salvajes', 'del Páramo', 'Lunares', 'del Río',
    'Solares', 'de Cristal', 'Urbanos', 'del Desierto', 'Errantes', 'de Fuego',
    'Silenciosos', 'del Norte', 'Brillantes', 'de Papel', 'Magnéticos', 'del Mar',
    'Invisibles', 'de Acero', 'Tropicales', 'del Viento', 'Perdidos', 'de Seda',
    'Dorados', 'del Bosque', 'Rebeldes', 'de Humo', 'Celestes', 'del Valle',
    'Imposibles', 'de Barro', 'Sinfónicos', 'de la Costa', 'Digitales', 'del Alba',
    'Mecánicos', 'de Plata', 'Lejanos', 'del Centro', 'Infinitos', 'de Arena',
    'Clandestinos', 'del Cerro', 'Polares', 'de Medianoche', 'Acústicos', 'de Ámbar',
    'Viajeros', 'del Lago', 'Ruidosos', 'de Cobre', 'Tranquilos', 'del Trópico',
    'Mágicos', 'de Granito', 'Felices', 'del Ocaso', 'Rápidos', 'de Terciopelo',
    'Antiguos', 'de la Sierra', 'Modernos', 'del Cielo', 'Futuros', 'de Jade',
    'Ocultos', 'de la Calle', 'Gigantes', 'del Faro', 'Pequeños', 'de Marfil',
    'Visibles', 'del Barrio', 'Distantes', 'de Bronce', 'Sonoros', 'de la Luna',
    'Ardientes', 'del Hielo', 'Fugaces', 'de Mármol', 'Secretos', 'de Tierra',
    'Libres', 'del Eco', 'Ligeros', 'de Lluvia', 'Profundos', 'del Trueno',
    'Eternos', 'de Coral', 'Leales', 'del Abismo',
]
PAISES = ['Ecuador', 'Colombia', 'Perú', 'México', 'Argentina', 'Chile', 'España',
          'Estados Unidos', 'Cuba', 'Puerto Rico', 'Brasil', 'Venezuela', 'Uruguay']
PALABRAS = [
    'amor', 'noche', 'luna', 'fuego', 'corazón', 'camino', 'cielo', 'sueño', 'mar',
    'ciudad', 'lluvia', 'sombra', 'viento', 'estrella', 'tiempo', 'ritmo', 'baile',
    'silencio', 'verano', 'invierno', 'recuerdo', 'destino', 'libertad', 'montaña',
    'río', 'ventana', 'madrugada', 'deseo', 'promesa', 'espejo', 'sol', 'calle',
    'tormenta', 'abrazo', 'distancia', 'mañana', 'secreto', 'alma', 'luz', 'regreso',
    'fiesta', 'volcán', 'tren', 'carta', 'canción', 'vida', 'pasión', 'horizonte',
    'nube', 'locura', 'despacio', 'eterno', 'perdido', 'brillante', 'salvaje',
    'dorado', 'azul', 'rojo', 'último', 'primer',
]
GENEROS = ['Pop', 'Rock', 'Reggaetón', 'Salsa', 'Bachata', 'Cumbia', 'Pasillo',
           'Electrónica', 'Hip hop', 'Jazz', 'Balada', 'Merengue', 'Indie',
           'Clásica', 'Metal', 'Bolero', 'Trap', 'Funk']


class Command(BaseCommand):
    help = 'Genera artistas y canciones de prueba con generate_series (por defecto 200.000 canciones).'

    def add_arguments(self, parser):
        parser.add_argument('--canciones', type=int, default=200_000)
        parser.add_argument('--artistas', type=int, default=3_000)
        parser.add_argument(
            '--reemplazar', action='store_true',
            help='Borra antes TODAS las canciones, artistas y su contenido en playlists.'
        )

    def handle(self, *args, **opciones):
        n_canciones = opciones['canciones']
        n_artistas = opciones['artistas']
        maximo_artistas = len(PREFIJOS) * len(NUCLEOS)
        if not 1 <= n_artistas <= maximo_artistas:
            raise CommandError(f'--artistas debe estar entre 1 y {maximo_artistas}.')

        t_artista = Artista._meta.db_table
        t_cancion = Cancion._meta.db_table
        t_pc = PlaylistCancion._meta.db_table
        inicio = time.perf_counter()

        with transaction.atomic(), connection.cursor() as cursor:

            if opciones['reemplazar']:
                self.stdout.write('Borrando el catálogo actual...')
                # TRUNCATE vacía las tablas al instante (no fila por fila) y
                # RESTART IDENTITY reinicia los id en 1.
                cursor.execute(f'TRUNCATE {t_pc}, {t_cancion}, {t_artista} RESTART IDENTITY CASCADE;')

            # setseed: los números aleatorios salen iguales en cada ejecución,
            # así todos los estudiantes obtienen los mismos datos.
            cursor.execute('SELECT setseed(0.42);')

            # ------------------------------------------------ Artistas
            # Cada número i produce una combinación distinta de prefijo y
            # núcleo ("Los Andinos", "Banda del Sur"...), así no se repiten.
            self.stdout.write(f'Insertando {n_artistas:,} artistas...'.replace(',', '.'))
            cursor.execute(f"""
                INSERT INTO {t_artista} (nombre, pais)
                SELECT
                    (%(prefijos)s::text[])[1 + (i %% %(np)s)]
                        || ' ' || (%(nucleos)s::text[])[1 + (i / %(np)s)],
                    (%(paises)s::text[])[1 + floor(random() * %(npa)s)::int]
                FROM generate_series(0, %(n)s - 1) AS i
                WHERE NOT EXISTS (
                    SELECT 1 FROM {t_artista} a
                    WHERE upper(a.nombre) = upper(
                        (%(prefijos)s::text[])[1 + (i %% %(np)s)]
                        || ' ' || (%(nucleos)s::text[])[1 + (i / %(np)s)])
                );
            """, {
                'prefijos': PREFIJOS, 'nucleos': NUCLEOS, 'paises': PAISES,
                'np': len(PREFIJOS), 'npa': len(PAISES), 'n': n_artistas,
            })

            cursor.execute(f'SELECT array_agg(id_artista) FROM {t_artista};')
            ids_artistas = cursor.fetchone()[0]

            # ------------------------------------------------ Canciones
            # El título combina 2 o 3 palabras al azar ("Luna salvaje",
            # "Camino de amor"...). La consulta interna arma el texto y la
            # externa pone en mayúscula solo la primera letra.
            self.stdout.write(f'Insertando {n_canciones:,} canciones...'.replace(',', '.'))
            cursor.execute(f"""
                INSERT INTO {t_cancion}
                    (titulo, id_artista, genero, anio, duracion_segundos, popularidad)
                SELECT upper(left(t, 1)) || substr(t, 2),
                       id_artista, genero, anio, duracion, popularidad
                FROM (
                    SELECT
                        p[1 + floor(random() * np)::int] || ' ' ||
                        CASE WHEN random() < 0.3 THEN 'de ' ELSE '' END ||
                        p[1 + floor(random() * np)::int] ||
                        CASE WHEN random() < 0.4 THEN ' ' || p[1 + floor(random() * np)::int]
                             ELSE '' END                          AS t,
                        ids[1 + floor(random() * nids)::int]      AS id_artista,
                        g[1 + floor(random() * ng)::int]          AS genero,
                        1960 + floor(random() * 67)::int          AS anio,      -- 1960 a 2026
                        120 + floor(random() * 300)::int          AS duracion,  -- 2:00 a 6:59
                        CASE WHEN random() < 0.02 THEN NULL                     -- 2%% sin dato
                             ELSE floor(random() * 101)::int END  AS popularidad
                    FROM generate_series(1, %(n)s) AS i,
                         (SELECT %(palabras)s::text[] AS p, %(np)s AS np,
                                 %(generos)s::text[] AS g, %(ng)s AS ng,
                                 %(ids)s::int[] AS ids, %(nids)s AS nids) AS datos
                ) AS generadas;
            """, {
                'palabras': PALABRAS, 'np': len(PALABRAS),
                'generos': GENEROS, 'ng': len(GENEROS),
                'ids': ids_artistas, 'nids': len(ids_artistas), 'n': n_canciones,
            })

        # ANALYZE actualiza las estadísticas que usa el planificador de
        # PostgreSQL para decidir si conviene un índice o un Seq Scan.
        # Se ejecuta fuera de la transacción.
        with connection.cursor() as cursor:
            cursor.execute(f'ANALYZE {t_artista}; ANALYZE {t_cancion};')

        cache.delete('generos')
        segundos = time.perf_counter() - inicio
        total = Cancion.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f'Listo en {segundos:.1f} s. La tabla {t_cancion} tiene ahora '
            f'{total:,} filas.'.replace(',', '.')
        ))
        self.stdout.write('Siguiente paso: python manage.py comparar_indices')
