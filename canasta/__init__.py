import random

from otree.api import *

from nucleo import ajustes_otree, tablero, tiempo
from nucleo.formato import numero, pesos, porcentaje

from . import devolucion, modelo

# Página propia para "aula completa" (ver nucleo/ajustes_otree.py).
ajustes_otree.aplicar()


doc = """
La canasta de Soledad (FCEJ - UNLPam), Microeconomía (unidades II y III).
Cada equipo es un consumidor que reparte su ingreso del mes entre entradas al cine y alimentos.
Cada mes cambian los precios o el ingreso; el equipo elige cuántas entradas compra mirando sus curvas
de indiferencia y la recta de presupuesto. Puntos por acercarse a la canasta óptima y por la pregunta
del mes (TMS, elasticidades, efecto sustitución).
"""


class C(BaseConstants):
    NAME_IN_URL = 'canasta'
    # Todos los equipos frente a los mismos precios, pasando juntos de mes.
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = len(modelo.RONDAS)
    TITULO_JUEGO = 'La canasta de Soledad'
    SUBTITULO_JUEGO = 'Comportamiento del consumidor'


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    nombre_equipo = models.StringField(label='Nombre del equipo', max_length=30, blank=True)

    # Decisión del mes
    entradas = models.IntegerField(min=0, max=1000, label='Entradas al cine que compran en el mes')
    respuesta = models.FloatField(label='Su respuesta', blank=True, min=-1e12, max=1e12)

    # Resultados del mes
    puntos = models.IntegerField()
    acierto = models.BooleanField()
    puntaje = models.FloatField()
    # No enviaron a tiempo: la decisión la tomó el sistema al azar (ver nucleo/tiempo.py).
    fuera_de_tiempo = models.BooleanField(initial=False)


# --- Funciones auxiliares ---------------------------------------------------

def num_rondas(session):
    return min(session.config.get('num_rondas', len(modelo.RONDAS)), C.NUM_ROUNDS)


def ronda_activa(player):
    return player.round_number <= num_rondas(player.session)


def es_ultima_ronda(player):
    return player.round_number == num_rondas(player.session)


def parametros(session):
    return {k: session.config[k] for k in modelo.PARAMETROS}


def nombre(player):
    return player.participant.vars.get('nombre_equipo') or f'Equipo {player.id_in_group}'


def tipo(player):
    return modelo.tipo_de_equipo(player.id_in_group)


def rondas_jugadas(player):
    return player.participant.vars.get('rondas_canasta', [])


def x_marzo(player):
    rs = rondas_jugadas(player)
    return rs[0]['x'] if rs else None


def datos_del_mes(player, ronda=None):
    ronda = ronda or player.round_number
    return modelo.datos_ronda(ronda, parametros(player.session), x_marzo(player) if ronda > 1 else None)


def nombre_ronda(ronda):
    r = modelo.RONDAS[ronda - 1]
    return f'{r["mes"]}: {r["titulo"].lower()}'


def num(x):
    """3 → '3'; 2.5 → '2,5'; 2.333 → '2,33'."""
    if abs(x - round(x)) < 1e-9:
        return numero(x, 0)
    if abs(x * 10 - round(x * 10)) < 1e-9:
        return numero(x, 1)
    return numero(x, 2)


def texto_valor(valor, unidad):
    if valor is None:
        return 'sin respuesta'
    if unidad == '(número)':
        return numero(valor, 2)
    return f'{num(valor)} {unidad}'


def decision_al_azar(player):
    """Entradas al azar dentro del presupuesto (cuando el equipo no envía a tiempo), sin respuesta."""
    player.entradas = random.randint(0, datos_del_mes(player)['x_max'])
    player.respuesta = None
    player.fuera_de_tiempo = True
    tiempo.marcar_fuera_de_tiempo(player.participant.vars, player.round_number)


# --- Cierre del mes -------------------------------------------------------------------------

def cerrar_ronda(group: Group):
    p = parametros(group.session)
    for pl in group.get_players():
        r = modelo.jugar_ronda(pl.round_number, pl.entradas, pl.field_maybe_none('respuesta'), tipo(pl), p,
                               x_marzo(pl))
        r['fuera_de_tiempo'] = bool(pl.fuera_de_tiempo)
        rondas = rondas_jugadas(pl) + [r]
        pl.participant.vars['rondas_canasta'] = rondas
        pl.puntos = r['puntos']
        pl.acierto = r['pregunta']['acierto']
        pl.puntaje = modelo.puntaje(rondas, p)
    # El reloj de la ronda siguiente corre desde ahora, igual para todos.
    if group.round_number < num_rondas(group.session):
        tiempo.abrir_ronda([pl.participant.vars for pl in group.get_players()], group.round_number + 1,
                           group.session.config)
    for pl in group.get_players():
        actualizar_tablero(pl, 'Resultados listos')


def puntajes(player):
    """Puntaje de cada equipo con lo acumulado hasta ahora: {id_in_group: puntos de 0 a 100}."""
    p = parametros(player.session)
    return {q.id_in_group: modelo.puntaje(q.participant.vars['rondas_canasta'], p)
            for q in player.group.get_players() if q.participant.vars.get('rondas_canasta')}


def puesto(player):
    pts = puntajes(player)
    if player.id_in_group not in pts:
        return None
    orden = sorted(pts, key=pts.get, reverse=True)
    return orden.index(player.id_in_group) + 1


# --- Datos para las pantallas ----------------------------------------------------------------

def datos_tabla(d):
    filas = [
        ('Ingreso del mes', pesos(d['ingreso'])),
        ('Precio de la entrada al cine (Px)', pesos(d['px'])),
        ('Precio de la canasta de alimentos (Py)', pesos(d['py'])),
        ('Recta de presupuesto', f'{pesos(d["px"])} · X + {pesos(d["py"])} · Y = {pesos(d["ingreso"])}'),
        ('Entradas como máximo', f'{d["x_max"]} (si no compran alimentos)'),
    ]
    return [dict(concepto=a, valor=b) for a, b in filas]


def datos_grafico(d, t, x_marcado=None, x_opt=None):
    """Lo que necesita el gráfico de la canasta (curvas de indiferencia y recta de presupuesto)."""
    x_o, y_o, u_o = modelo.optimo(d, t)
    info = modelo.TIPOS[t]
    return dict(a=info['a'], sigma=info['sigma'], ingreso=d['ingreso'], px=d['px'], py=d['py'],
                x_max=d['x_max'], y_max=d['ingreso'] / d['py'], niveles=modelo.niveles_curvas(u_o),
                x_marcado=x_marcado, x_opt=x_opt, u_opt=u_o if x_opt is not None else None)


def curvas_del_equipo(rondas):
    """Puntos de la demanda (Px, X) con el ingreso de marzo y de la curva de Engel (I, X) con los precios de
    marzo, de las decisiones del equipo y del modelo."""
    demanda = sorted([(r['px'], r['x'], r['x_opt']) for r in rondas if r['ronda'] in (1, 2, 3)])
    engel = sorted([(r['ingreso'], r['x'], r['x_opt']) for r in rondas if r['ronda'] in (1, 4, 5)])
    return demanda, engel


# --- Tablero del docente y devolución ---------------------------------------------------

ETAPAS_TABLERO = {
    'Instrucciones': ('decidiendo', 'Leyendo instrucciones'),
    'Decisión': ('decidiendo', 'Eligiendo la canasta del mes'),
    'Esperando a los demás equipos': ('esperando', 'Decisión enviada'),
    'Resultados listos': ('resultados', 'Resultados del mes listos'),
    'Viendo resultados': ('resultados', 'Viendo resultados'),
    'Terminó': ('termino', 'Terminó'),
}

COLUMNAS_TABLERO = [
    tablero.columna('ronda', 'M', 'ronda'),
    tablero.columna('mes', 'Mes', 'texto'),
    tablero.columna('entradas', 'Entradas (óptimo)', 'texto'),
    tablero.columna('utilidad', 'Ingreso real logrado', 'texto'),
    tablero.columna('puntos', 'Puntos', 'texto'),
    tablero.columna('pregunta', 'Pregunta', 'texto'),
    tablero.columna('envio', 'Envío', 'texto'),
]


def historial(player):
    return [dict(ronda=r['ronda'], mes=r['mes'], entradas=f'{r["x"]} ({r["x_opt"]})',
                 utilidad=porcentaje(r['relativa'], 1), puntos=str(r['puntos']),
                 pregunta='✓' if r['pregunta']['acierto'] else '✗',
                 envio='⏱ al azar' if r.get('fuera_de_tiempo') else 'a tiempo')
            for r in rondas_jugadas(player)]


def devolucion_de(player):
    rondas = rondas_jugadas(player)
    if not rondas:
        return []
    obs = devolucion.diagnosticar(rondas, parametros(player.session), tipo(player), puesto(player),
                                  len(player.group.get_players()))
    return obs + tiempo.observaciones(player.participant.vars, 'M')


def actualizar_tablero(player, pagina):
    etapa, estado_txt = ETAPAS_TABLERO[pagina]
    rondas = rondas_jugadas(player)
    pts = puntajes(player)
    jugo = bool(rondas)
    player.participant.vars['tablero'] = tablero.resumen(
        juego=C.NAME_IN_URL,
        equipo=nombre(player),
        grupo_numero=player.group.id_in_subsession,
        grupo_tipo='grupo',
        grupo_tamano=len(player.group.get_players()),
        posicion=player.id_in_group,
        ronda=player.round_number,
        rondas=num_rondas(player.session),
        nombre_ronda='mes', abrev_ronda='M',
        etapa=etapa,
        estado=estado_txt,
        puesto=puesto(player),
        indicadores=[
            tablero.indicador('Consumidor', modelo.TIPOS[tipo(player)]['nombre'], 'texto'),
            tablero.indicador('Canastas óptimas', sum(1 for r in rondas if r['distancia'] == 0) if jugo else None,
                              'numero'),
            tablero.indicador('Preguntas', sum(1 for r in rondas if r['pregunta']['acierto']) if jugo else None,
                              'numero'),
            tablero.indicador('Puntaje', numero(pts[player.id_in_group], 1) if player.id_in_group in pts else None,
                              'texto'),
        ],
        decision=None,
        columnas=COLUMNAS_TABLERO,
        filas=historial(player),
        nota_historial='Entre paréntesis, la cantidad óptima de entradas del tipo de consumidor del equipo. '
                       '"Ingreso real logrado" = U(elegida) / U(óptima).',
        devolucion=devolucion_de(player),
        vence=tiempo.vence_pendiente(player.participant.vars, player.session.config, player.round_number,
                                     etapa, es_ultima_ronda(player)),
        fuera_de_tiempo=tiempo.rondas_fuera_de_tiempo(player.participant.vars),
    )


# --- Páginas ------------------------------------------------------------------------------

class Instrucciones(Page):
    form_model = 'player'
    form_fields = ['nombre_equipo']
    timer_text = tiempo.TEXTO_DECISION

    @staticmethod
    def get_timeout_seconds(player: Player):
        return tiempo.segundos_decision(player.participant.vars, player.session.config, player.round_number)

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Instrucciones')
        p = parametros(player.session)
        t = modelo.TIPOS[tipo(player)]
        n = num_rondas(player.session)
        return dict(
            **tiempo.contexto(player.session.config, 'mes'),
            num_rondas=n, num_equipos=len(player.group.get_players()),
            tipo_nombre=t['nombre'], tipo_descripcion=t['descripcion'],
            ingreso=pesos(p['ingreso_base']), precio_cine=pesos(p['precio_cine']),
            precio_alimentos=pesos(p['precio_alimentos']),
            meses=[dict(mes=r['mes'], titulo=r['titulo']) for r in modelo.RONDAS[:n]],
            puntos_exacto=p['puntos_exacto'], puntos_a_uno=p['puntos_a_uno'], puntos_a_dos=p['puntos_a_dos'],
            tolerancia=porcentaje(p['tolerancia_pregunta'], 0), puntos_pregunta=p['puntos_pregunta'],
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        texto = (player.nombre_equipo or '').strip()
        if texto:
            player.participant.vars['nombre_equipo'] = texto


class Decision(Page):
    form_model = 'player'
    form_fields = ['entradas', 'respuesta']
    timer_text = tiempo.TEXTO_DECISION

    @staticmethod
    def get_timeout_seconds(player: Player):
        return tiempo.segundos_decision(player.participant.vars, player.session.config, player.round_number)

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)

    @staticmethod
    def error_message(player: Player, values):
        d = datos_del_mes(player)
        if values['entradas'] > d['x_max']:
            return (f'Con {pesos(d["ingreso"])} alcanza para {d["x_max"]} entradas como máximo '
                    f'({pesos(d["px"])} cada una).')

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Decisión')
        p = parametros(player.session)
        ronda = player.round_number
        d = datos_del_mes(player)
        xm = x_marzo(player)
        pregunta, _, unidad, _ = modelo.pregunta_de_la_ronda(ronda, p, xm if xm is not None else 0, 0)
        anterior = rondas_jugadas(player)[-1] if rondas_jugadas(player) else None
        t = modelo.TIPOS[tipo(player)]
        return dict(
            **tiempo.contexto(player.session.config, 'mes'),
            num_rondas=num_rondas(player.session), mes=nombre_ronda(ronda),
            anuncio=d['anuncio'], compensada=d['compensada'],
            datos=datos_tabla(d),
            tipo_nombre=t['nombre'], tipo_descripcion=t['descripcion'],
            x_marzo=xm, hay_marzo=xm is not None and ronda > 2,
            entradas_anteriores=anterior['x'] if anterior else None, hay_anterior=anterior is not None,
            x_max=d['x_max'],
            pregunta=pregunta, unidad=unidad,
            tolerancia=porcentaje(p['tolerancia_pregunta'], 0), puntos_pregunta=p['puntos_pregunta'],
            puntaje=numero(player.in_round(ronda - 1).puntaje, 1) if anterior else None,
        )

    @staticmethod
    def js_vars(player: Player):
        return datos_grafico(datos_del_mes(player), tipo(player))

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        if timeout_happened:
            decision_al_azar(player)
        actualizar_tablero(player, 'Esperando a los demás equipos')


class EsperaRonda(WaitPage):
    title_text = 'Esperando a los demás equipos'
    body_text = 'Los resultados del mes aparecen cuando todos los equipos hayan elegido su canasta.'
    after_all_players_arrive = cerrar_ronda

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)


class Resultados(Page):
    timer_text = tiempo.TEXTO_LECTURA

    @staticmethod
    def get_timeout_seconds(player: Player):
        # El reloj de la ronda siguiente ya corre mientras leen los resultados.
        return tiempo.segundos_lectura(player.participant.vars, player.round_number, es_ultima_ronda(player))

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Viendo resultados')
        rondas = rondas_jugadas(player)
        r = rondas[-1]
        p = parametros(player.session)
        preg = r['pregunta']
        demanda, engel = curvas_del_equipo(rondas)
        return dict(
            **tiempo.contexto(player.session.config, 'mes'),
            t_fuera=r.get('fuera_de_tiempo', False),
            num_rondas=num_rondas(player.session), mes=nombre_ronda(r['ronda']),
            x=r['x'], y=num(r['y']), gasto_cine=pesos(r['gasto_cine']),
            gasto_alimentos=pesos(r['ingreso'] - r['gasto_cine']),
            x_opt=r['x_opt'], y_opt=num(r['y_opt']), x_continuo=numero(r['x_continuo'], 2),
            es_optima=r['distancia'] == 0,
            relativa=porcentaje(r['relativa'], 1), ingreso_perdido=pesos(r['ingreso_perdido']),
            hay_perdida=r['ingreso_perdido'] >= 1,
            tms_elegida=numero(r['tms_elegida'], 2) if r['tms_elegida'] is not None else None,
            precio_relativo=num(r['precio_relativo']),
            puntos=r['puntos'], puntos_exacto=p['puntos_exacto'],
            pregunta=preg['texto'], correcto=texto_valor(preg['correcto'], preg['unidad']),
            anulada=preg['correcto'] is None,
            respuesta=texto_valor(preg['respuesta'], preg['unidad']), acierto=preg['acierto'],
            absoluto=preg['absoluto'], puntos_pregunta=p['puntos_pregunta'],
            demanda=[dict(px=pesos(a), x=b, opt=c) for a, b, c in demanda] if len(demanda) > 1 else None,
            engel=[dict(ingreso=pesos(a), x=b, opt=c) for a, b, c in engel] if len(engel) > 1 else None,
            puntaje=numero(player.puntaje, 1),
            puesto=puesto(player), num_equipos=len(player.group.get_players()),
        )

    @staticmethod
    def js_vars(player: Player):
        r = rondas_jugadas(player)[-1]
        d = modelo.datos_ronda(r['ronda'], parametros(player.session), x_marzo(player) if r['ronda'] > 1 else None)
        return datos_grafico(d, r['tipo'], x_marcado=r['x'], x_opt=r['x_opt'])


class ResultadoFinal(Page):
    @staticmethod
    def is_displayed(player: Player):
        return es_ultima_ronda(player)

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Terminó')
        pts = puntajes(player)
        equipos = sorted(player.group.get_players(), key=lambda q: pts.get(q.id_in_group, 0), reverse=True)
        filas = []
        for i, q in enumerate(equipos):
            rs = q.participant.vars.get('rondas_canasta', [])
            filas.append(dict(puesto=i + 1, nombre=nombre(q), es_propia=q.id_in_group == player.id_in_group,
                              tipo=modelo.TIPOS[tipo(q)]['nombre'],
                              puntaje=numero(pts.get(q.id_in_group, 0), 1),
                              optimas=sum(1 for r in rs if r['distancia'] == 0),
                              relativa=porcentaje(sum(r['relativa'] for r in rs) / max(1, len(rs)), 1),
                              preguntas=sum(1 for r in rs if r['pregunta']['acierto'])))
        rondas = rondas_jugadas(player)
        return dict(
            t_fuera_lista=tiempo.lista(player.participant.vars, 'M'),
            ranking=filas,
            tipo_nombre=modelo.TIPOS[tipo(player)]['nombre'],
            optimas=sum(1 for r in rondas if r['distancia'] == 0),
            aciertos=sum(1 for r in rondas if r['pregunta']['acierto']), num_rondas=len(rondas),
            puntaje=numero(player.puntaje, 1),
            rondas=[dict(mes=nombre_ronda(r['ronda']), ingreso=pesos(r['ingreso']), px=pesos(r['px']),
                         py=pesos(r['py']), x=r['x'], opt=r['x_opt'], relativa=porcentaje(r['relativa'], 1),
                         puntos=r['puntos'], pregunta='✓' if r['pregunta']['acierto'] else '✗') for r in rondas],
            demanda_clase=demanda_de_la_clase(player),
            devolucion=devolucion_de(player),
            comentario_docente=(player.participant.vars.get('comentario_docente') or '').strip(),
        )

    @staticmethod
    def js_vars(player: Player):
        demanda, engel = curvas_del_equipo(rondas_jugadas(player))
        clase = demanda_de_la_clase(player)
        return dict(
            demanda=[[a, b, c] for a, b, c in demanda], engel=[[a, b, c] for a, b, c in engel],
            clase=[[f['px_valor'], f['total'], f['total_opt']] for f in clase],
        )


def demanda_de_la_clase(player):
    """Suma horizontal de las demandas de cine de todos los equipos, con el ingreso de marzo (meses 1 a 3)."""
    filas = {}
    for q in player.group.get_players():
        for r in q.participant.vars.get('rondas_canasta', []):
            if r['ronda'] in (1, 2, 3):
                f = filas.setdefault(r['px'], dict(px_valor=r['px'], px=pesos(r['px']), total=0, total_opt=0,
                                                   equipos=0))
                f['total'] += r['x']
                f['total_opt'] += r['x_opt']
                f['equipos'] += 1
    return [filas[k] for k in sorted(filas)]


page_sequence = [Instrucciones, Decision, EsperaRonda, Resultados, ResultadoFinal]
