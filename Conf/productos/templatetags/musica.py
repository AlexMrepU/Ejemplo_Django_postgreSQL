from django import template

register = template.Library()


@register.filter
def duracion(segundos):
    """Convierte segundos a formato m:ss (o h:mm:ss). Ej.: 218 -> 3:38."""
    if segundos in (None, ''):
        return '-'
    segundos = int(segundos)
    horas, resto = divmod(segundos, 3600)
    minutos, seg = divmod(resto, 60)
    if horas:
        return f'{horas}:{minutos:02d}:{seg:02d}'
    return f'{minutos}:{seg:02d}'


@register.simple_tag(takes_context=True)
def url_pagina(context, numero):
    """
    Enlace a otra página conservando los filtros actuales.
    Ej.: en /canciones/?q=amor&genero=Pop&page=2 -> ?q=amor&genero=Pop&page=3
    Sin esto, al pasar de página se perderían la búsqueda y los filtros.
    """
    parametros = context['request'].GET.copy()
    parametros['page'] = numero
    return '?' + parametros.urlencode()


@register.filter
def portada(id_playlist):
    """
    Color de la portada de una playlist, calculado a partir de su id.
    Siempre da el mismo tono para la misma playlist (no necesita imagen).
    Se usa como variable CSS: style="--tono: {{ playlist.id_playlist|portada }}"
    """
    try:
        return (int(id_playlist) * 47) % 360
    except (TypeError, ValueError):
        return 200


@register.filter
def miles(numero):
    """Separador de miles con punto, como se escribe en Ecuador: 200000 -> 200.000"""
    try:
        return f'{int(numero):,}'.replace(',', '.')
    except (TypeError, ValueError):
        return numero
