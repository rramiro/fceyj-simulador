"""
Ajustes puntuales sobre oTree (sin modificar sus archivos).

Aula completa
-------------
Cuando entra a una sesión o aula más gente que lugares, oTree responde con el
texto "La sesión está llena." en una respuesta sin Content-Type: el navegador
no sabe que es UTF-8 y muestra "La sesiÃ³n estÃ¡ llena.". Acá se reemplaza esa
respuesta por una página con la estética de la Facultad
(_templates/global/AulaLlena.html), en UTF-8 y con el mismo código 404 que usa
oTree (sus bots y pruebas dependen de él).

oTree llama a otree.views.participant.no_participants_left_http_response()
cada vez que no queda lugar; como la busca por nombre en su módulo, alcanza con
reemplazarla. Revisar si se actualiza oTree (versión probada: la de requirements.txt).
"""
import logging

logger = logging.getLogger(__name__)


def respuesta_aula_llena():
    from otree.templating import render

    respuesta = render('global/AulaLlena.html', {})
    respuesta.status_code = 404
    return respuesta


def aplicar():
    try:
        import otree.views.participant as vistas
    except ImportError:  # pragma: no cover - versión de oTree muy distinta
        logger.warning('ajustes_otree: no se encontró otree.views.participant; se deja el mensaje original.')
        return
    if hasattr(vistas, 'no_participants_left_http_response'):
        vistas.no_participants_left_http_response = respuesta_aula_llena
    else:  # pragma: no cover
        logger.warning('ajustes_otree: oTree cambió; no se reemplazó el mensaje de aula completa.')
