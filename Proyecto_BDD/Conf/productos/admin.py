from django.contrib import admin

from .models import Artista, Cancion, Playlist, PlaylistCancion


@admin.register(Artista)
class ArtistaAdmin(admin.ModelAdmin):
    list_display = ('id_artista', 'nombre', 'pais')
    search_fields = ('nombre',)


@admin.register(Cancion)
class CancionAdmin(admin.ModelAdmin):
    list_display = ('id_cancion', 'titulo', 'artista', 'genero', 'anio', 'popularidad')
    list_select_related = ('artista',)
    search_fields = ('titulo',)
    autocomplete_fields = ('artista',)  # evita un <select> con miles de artistas
    list_filter = ('genero',)
    ordering = ('titulo',)


class PlaylistCancionInline(admin.TabularInline):
    model = PlaylistCancion
    extra = 1
    autocomplete_fields = ('cancion',)


@admin.register(Playlist)
class PlaylistAdmin(admin.ModelAdmin):
    list_display = ('id_playlist', 'nombre', 'propietario', 'publica', 'creada')
    list_filter = ('publica',)
    list_select_related = ('propietario',)
    inlines = [PlaylistCancionInline]
    search_fields = ('nombre', 'propietario__username')
    autocomplete_fields = ('propietario',)
