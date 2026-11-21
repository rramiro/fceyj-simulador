"""
Tiempo máximo por ronda (común a todos los juegos).

El docente fija en la sesión `minutos_por_ronda` (0 = sin límite) y, si quiere,
`minutos_primera_ronda` para la primera (0 = los mismos minutos que las demás).

Cuándo corre el reloj
---------------------
- Ronda 1: para cada equipo, desde que abre la primera página (las instrucciones),
  porque los equipos entran al aula en distintos momentos.
- Rondas siguientes: un reloj común a todo el grupo, desde que se publican los
  resultados de la ronda anterior (lo fija la función que cierra la ronda).

Todas las páginas de la ronda hasta el envío de la decisión, incluidos los resultados
de la ronda anterior, comparten ese vencimiento: cada página tiene como tiempo límite
"vencimiento − ahora". Si vence, oTree envía la página solo (también con el navegador
cerrado: lo hace el proceso de tiempos del servidor, que corre con `otree prodserver`
pero no con `otree devserver`), y el juego completa la decisión al azar y marca la
ronda como fuera de tiempo.

Los vencimientos se guardan en participant.vars['vencimientos'] = {'<ronda>': segundos
desde 1970}; las rondas fuera de tiempo, en participant.vars['fuera_de_tiempo'] = [rondas].

No importa oTree: así los scripts y las pruebas pueden usarlo sin el servidor.
"""
import time

# Tiempo mínimo de una página cuando el vencimiento ya pasó: oTree la envía enseguida.
MINIMO = 1

TEXTO_DECISION = 'Tiempo para enviar la decisión:'
TEXTO_LECTURA = 'Tiempo para leer y enviar la próxima decisión:'


def minutos_por_ronda(config):
    return max(0.0, float(config.get('minutos_por_ronda') or 0))


def minutos_primera_ronda(config):
    return max(0.0, float(config.get('minutos_primera_ronda') or 0)) or minutos_por_ronda(config)


def hay_limite(config):
    return minutos_por_ronda(config) > 0


def vencimiento(pvars, ronda):
    """Segundos desde 1970 en que vence la ronda, o None si no tiene límite (o todavía no empezó)."""
    return (pvars.get('vencimientos') or {}).get(str(ronda))


def fijar_vencimiento(pvars, ronda, segundos, ahora=None):
    """Fija (o reemplaza) el vencimiento de la ronda y lo devuelve."""
    venc = (time.time() if ahora is None else ahora) + segundos
    vencimientos = dict(pvars.get('vencimientos') or {})
    vencimientos[str(ronda)] = venc
    pvars['vencimientos'] = vencimientos
    return venc


def iniciar_primera_ronda(pvars, config, ahora=None):
    """Arranca el reloj de la ronda 1 del equipo (solo la primera vez). Devuelve el vencimiento."""
    if not hay_limite(config):
        return None
    venc = vencimiento(pvars, 1)
    if venc is None:
        venc = fijar_vencimiento(pvars, 1, minutos_primera_ronda(config) * 60, ahora)
    return venc


def abrir_ronda(pvars_de_todos, ronda, config, ahora=None):
    """Al publicar los resultados de la ronda anterior: mismo vencimiento para todo el grupo."""
    if not hay_limite(config):
        return None
    ahora = time.time() if ahora is None else ahora
    for pvars in pvars_de_todos:
        fijar_vencimiento(pvars, ronda, minutos_por_ronda(config) * 60, ahora)
    return ahora + minutos_por_ronda(config) * 60


def segundos_restantes(venc, ahora=None):
    """Tiempo límite de una página (None = sin límite)."""
    if venc is None:
        return None
    return max(MINIMO, venc - (time.time() if ahora is None else ahora))


def marcar_fuera_de_tiempo(pvars, ronda):
    rondas = list(pvars.get('fuera_de_tiempo') or [])
    if ronda not in rondas:
        rondas.append(ronda)
    pvars['fuera_de_tiempo'] = rondas
    return rondas


def rondas_fuera_de_tiempo(pvars):
    return list(pvars.get('fuera_de_tiempo') or [])


def texto_minutos(minutos):
    m = float(minutos)
    if m < 1:
        return f'{round(m * 60)} segundos'
    if m == int(m):
        m = int(m)
        return f'{m} minuto' + ('' if m == 1 else 's')
    return f'{m:.1f}'.replace('.', ',') + ' minutos'
