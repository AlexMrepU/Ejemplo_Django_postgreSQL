from django.urls import path
from . import views

urlpatterns = [

    path('', views.inicio, name='inicio'),

    # ----------------------------------------------------------- Artistas
    path('artistas/', views.listar_artistas, name='listar_artistas'),
    path('artistas/crear/', views.crear_artista, name='crear_artista'),
    path('artistas/<int:id_artista>/editar/', views.editar_artista, name='editar_artista'),
    path('artistas/<int:id_artista>/eliminar/', views.eliminar_artista, name='eliminar_artista'),

    # ----------------------------------------------------------- Canciones
    path('canciones/', views.listar_canciones, name='listar_canciones'),
    path('canciones/buscar/', views.buscar_canciones, name='buscar_canciones'),
    path('canciones/crear/', views.crear_cancion, name='crear_cancion'),
    path('canciones/<int:id_cancion>/editar/', views.editar_cancion, name='editar_cancion'),
    path('canciones/<int:id_cancion>/eliminar/', views.eliminar_cancion, name='eliminar_cancion'),

    # ----------------------------------------------------------- Playlists
    path('playlists/', views.listar_playlists, name='listar_playlists'),
    path('playlists/explorar/', views.explorar_playlists, name='explorar_playlists'),
    path('playlists/crear/', views.crear_playlist, name='crear_playlist'),
    path('playlists/<int:id_playlist>/', views.detalle_playlist, name='detalle_playlist'),
    path('playlists/<int:id_playlist>/editar/', views.editar_playlist, name='editar_playlist'),
    path('playlists/<int:id_playlist>/eliminar/', views.eliminar_playlist, name='eliminar_playlist'),

    # Canciones dentro de una playlist
    path('playlists/<int:id_playlist>/agregar/', views.agregar_cancion, name='agregar_cancion'),
    path(
        'playlists/<int:id_playlist>/quitar/<int:id_cancion>/',
        views.quitar_cancion,
        name='quitar_cancion'
    ),
    path(
        'playlists/<int:id_playlist>/mover/<int:id_cancion>/<str:direccion>/',
        views.mover_cancion,
        name='mover_cancion'
    ),
]
