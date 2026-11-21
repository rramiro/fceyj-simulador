import random

from otree.api import *

from nucleo import ajustes_otree, tablero
from nucleo.formato import numero, pesos, porcentaje

from . import devolucion, modelo

# Página propia para "aula completa" (ver nucleo/ajustes_otree.py).
ajustes_otree.aplicar()


doc = """
El depósito (FCEJ - UNLPam), Métodos Cuantitativos para la Administración.
Cada equipo maneja el depósito de un mueble de cocina. Cada mes fija el tamaño del
lote (n) y el punto de pedido (R); la demanda diaria y la demora del proveedor son
aleatorias. Un evento por mes (descuento por cantidad, suba de costos, campaña,
huelga) y una pregunta para calcular con las fórmulas del modelo.
"""

EMPRESA = 'Quantum Amoblamientos'
PRODUCTO = 'mueble de cocina de cedro'


class C(BaseConstants):
    NAME_IN_URL = 'deposito'
    # Todos los equipos frente a la misma demanda y pasando juntos de mes.
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 12
    TITULO_JUEGO = 'El depósito'
    SUBTITULO_JUEGO = f'Gestión de inventarios en {EMPRESA}'


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    nombre_equipo = models.StringField(label='Nombre del equipo', max_length=30, blank=True)

    # Decisiones del mes
    lote = models.IntegerField(min=1, max=5000, label='Tamaño del lote n (unidades por orden)')
    punto_pedido = models.IntegerField(min=0, max=5000, label='Punto de pedido R (unidades)')
    respuesta = models.FloatField(label='Su respuesta', blank=True, min=-1e12, max=1e12)

    # Resultados del mes
    costo = models.FloatField()
    costo_acumulado = models.FloatField()
    acierto = models.BooleanField()
    puntos_pregunta = models.IntegerField()


# --- Funciones auxiliares ---------------------------------------------------

def num_rondas(session):
    return min(session.config.get('num_rondas', 6), C.NUM_ROUNDS)


def ronda_activa(player):
    return player.round_number <= num_rondas(player.session)


def es_ultima_ronda(player):
    return player.round_number == num_rondas(player.session)


def parametros(session):
    return {k: session.config[k] for k in modelo.PARAMETROS}


def escenario(session):
    return session.vars['escenario']


def nombre(player):
    return player.participant.vars.get('nombre_equipo') or f'Equipo {player.id_in_group}'


def estado(player):
    """Estado del depósito al empezar el mes (se guarda en participant.vars)."""
    return player.participant.vars.get('estado_deposito') or modelo.estado_inicial(parametros(player.session))


def meses_jugados(player):
    return player.participant.vars.get('meses_deposito', [])


def evento_del_mes(player):
    return escenario(player.session)['eventos'][player.round_number - 1]['tipo']


def texto_valor(valor, unidad):
    if valor is None:
        return 'sin respuesta'
    if unidad.startswith('$'):
        return f'{pesos(valor)} {unidad[2:]}'.strip()
    return f'{numero(valor, 1)} {unidad}'


# --- Creación de la sesión -------------------------------------------------------------

def creating_session(subsession: Subsession):
    session = subsession.session
    if subsession.round_number == 1:
        semilla = int(session.config.get('semilla') or 0) or random.randint(1, 999_999)
        session.vars['semilla'] = semilla
        session.vars['escenario'] = modelo.generar_escenario(parametros(session), num_rondas(session), semilla)


# --- Cierre del mes ---------------------------------------------------------------------

def cerrar_mes(group: Group):
    p = parametros(group.session)
    esc = escenario(group.session)
    mes = group.round_number
    pregunta, correcto, unidad = modelo.pregunta_del_mes(mes, p, esc)
    n_rec, r_rec = modelo.politica_recomendada(mes, p, esc)
    for pl in group.get_players():
        antes = estado(pl)
        nuevo, r = modelo.simular_mes(mes, pl.lote, pl.punto_pedido, antes, p, esc)
        # Lo que habría costado la política "de manual" desde el mismo stock.
        _, rec = modelo.simular_mes(mes, n_rec, r_rec, antes, p, esc)
        acierto = modelo.acierta(pl.field_maybe_none('respuesta'), correcto, p)
        nuevo['aciertos'] = antes['aciertos'] + (1 if acierto else 0)
        r.update(pregunta=dict(texto=pregunta, correcto=correcto, unidad=unidad,
                               respuesta=pl.field_maybe_none('respuesta'), acierto=acierto),
                 recomendada=dict(lote=n_rec, punto_pedido=r_rec, costo=rec['costo'], perdidas=rec['perdidas']),
                 stock_inicial=antes['stock'])
        pl.participant.vars['estado_deposito'] = nuevo
        pl.participant.vars['meses_deposito'] = meses_jugados(pl) + [r]
        pl.costo = r['costo']
        pl.costo_acumulado = nuevo['costo_acumulado']
        pl.acierto = acierto
        pl.puntos_pregunta = nuevo['aciertos'] * p['puntos_pregunta']
    for pl in group.get_players():
        actualizar_tablero(pl, 'Resultados listos')


def puntajes(player):
    """Puntaje de cada equipo con lo acumulado hasta ahora: {id_in_group: puntos}."""
    equipos = [q for q in player.group.get_players() if q.participant.vars.get('estado_deposito')]
    if not equipos:
        return {}
    p = parametros(player.session)
    ests = [q.participant.vars['estado_deposito'] for q in equipos]
    pts = modelo.puntaje_final([e['costo_acumulado'] for e in ests],
                               [e['aciertos'] * p['puntos_pregunta'] for e in ests], p)
    return {q.id_in_group: x for q, x in zip(equipos, pts)}


def puesto(player):
    pts = puntajes(player)
    if player.id_in_group not in pts:
        return None
    orden = sorted(pts, key=pts.get, reverse=True)
    return orden.index(player.id_in_group) + 1


# --- Datos para las pantallas ----------------------------------------------------------

def texto_evento(mes, params, esc):
    d = modelo.datos_mes(mes, params, esc)
    p = params
    ev = d['evento']
    if ev == 'descuento':
        return (f'El proveedor ofrece un {porcentaje(p["descuento"], 0)} de descuento sobre el precio en una orden de '
                f'{numero(d["umbral"])} unidades o más (la primera del mes que alcance ese tamaño). Como el costo de '
                'mantener es un % del precio, con descuento también baja cm.')
    if ev == 'suba_co':
        return (f'Por el nuevo convenio del personal de Compras, emitir cada orden cuesta un {porcentaje(p["suba_co"], 0)} '
                f'más: {pesos(d["co"])} por orden.')
    if ev == 'campania':
        return (f'Lanzaron una campaña de ventas: este mes la demanda media sube a {numero(d["media_diaria"], 1)} '
                'unidades por día.')
    if ev == 'huelga':
        return (f'Hay una huelga en el transporte del proveedor: este mes la demora va de {d["demora_min"]} a '
                f'{d["demora_max"]} días hábiles.')
    if ev == 'tasa':
        return (f'Subió la tasa de interés: el costo de mantener pasa al {porcentaje(d["tasa"], 0)} anual del precio '
                f'({pesos(d["cm_dia"])} por unidad y por día).')
    return 'Sin novedades: valen los datos de siempre.'


def datos_tabla(mes, params, esc):
    d = modelo.datos_mes(mes, params, esc)
    cm_anual = d['cm_dia'] * params['dias_anio']
    filas = [
        ('Demanda media', f'{numero(d["media_diaria"], 1)} unidades por día hábil · D = {numero(d["D"])} por año'),
        ('Año (T)', f'{params["dias_anio"]} días hábiles; el mes tiene {params["dias_mes"]}'),
        ('Demora del proveedor', f'de {d["demora_min"]} a {d["demora_max"]} días hábiles (cualquier valor, igual probabilidad)'),
        ('Costo de adquisición ca', f'{pesos(d["precio"])} por unidad'),
        ('Costo de cada orden co', pesos(d['co'])),
        ('Costo de mantener cm', f'{porcentaje(d["tasa"], 0)} anual del precio: {pesos(cm_anual)} por unidad y por año '
                                 f'({pesos(d["cm_dia"])} por día)'),
        ('Costo del faltante c2', f'{pesos(d["c2"])} por unidad no vendida (se pierde la venta)'),
    ]
    if d['evento'] == 'descuento':
        filas.append(('Descuento', f'{porcentaje(params["descuento"], 0)} en una orden de {numero(d["umbral"])} unidades o más'))
    return [dict(concepto=a, valor=b) for a, b in filas]


def filas_costos(r):
    filas = [
        ('Órdenes emitidas', f'{len(r["ordenes"])} × co', pesos(r['costo_ordenes'])),
        ('Mantenimiento', f'stock promedio {numero(r["stock_promedio"], 1)} unidades', pesos(r['costo_mantener'])),
        ('Faltantes', f'{numero(r["perdidas"])} ventas perdidas × c2', pesos(r['costo_faltantes'])),
    ]
    if r['ahorro_descuento']:
        filas.append(('− Ahorro por descuento', '', pesos(-r['ahorro_descuento'])))
    return [dict(concepto=a, detalle=b, monto=c) for a, b, c in filas]


# --- Tablero del docente y devolución --------------------------------------------------

ETAPAS_TABLERO = {
    'Instrucciones': ('decidiendo', 'Leyendo instrucciones'),
    'Decisión': ('decidiendo', 'Decidiendo la política del mes'),
    'Esperando a los demás equipos': ('esperando', 'Política enviada'),
    'Resultados listos': ('resultados', 'Resultados del mes listos'),
    'Viendo resultados': ('resultados', 'Viendo resultados'),
    'Terminó': ('termino', 'Terminó'),
}

COLUMNAS_TABLERO = [
    tablero.columna('mes', 'M', 'ronda'),
    tablero.columna('evento', 'Evento', 'texto'),
    tablero.columna('politica', 'Política (n · R)', 'texto'),
    tablero.columna('costo', 'Costo del mes', 'pesos'),
    tablero.columna('servicio', 'Servicio', 'pct'),
    tablero.columna('pregunta', 'Pregunta', 'texto'),
]


def historial(player):
    return [dict(mes=r['mes'], evento=modelo.EVENTOS[r['evento']], politica=f'{r["lote"]} · {r["punto_pedido"]}',
                 costo=r['costo'], servicio=r['nivel_servicio'], pregunta='✓' if r['pregunta']['acierto'] else '✗')
            for r in meses_jugados(player)]


def devolucion_de(player):
    meses = meses_jugados(player)
    if not meses:
        return []
    return devolucion.diagnosticar(meses, estado(player), parametros(player.session), escenario(player.session),
                                   puesto(player), len(player.group.get_players()),
                                   terminado=len(meses) == num_rondas(player.session))


def actualizar_tablero(player, pagina):
    etapa, estado_txt = ETAPAS_TABLERO[pagina]
    est = estado(player)
    pts = puntajes(player)
    jugo = bool(meses_jugados(player))
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
            tablero.indicador('Costo acumulado', est['costo_acumulado'] if jugo else None, 'pesos'),
            tablero.indicador('Preguntas', est['aciertos'] if jugo else None, 'numero'),
            tablero.indicador('Puntaje', numero(pts[player.id_in_group], 1) if player.id_in_group in pts else None, 'texto'),
        ],
        decision=None,
        columnas=COLUMNAS_TABLERO,
        filas=historial(player),
        nota_historial='Costo de gestión del mes (órdenes + mantenimiento + faltantes − descuentos); el ranking usa el acumulado.',
        devolucion=devolucion_de(player),
    )


# --- Páginas --------------------------------------------------------------------------

class Instrucciones(Page):
    form_model = 'player'
    form_fields = ['nombre_equipo']

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Instrucciones')
        p = parametros(player.session)
        return dict(
            empresa=EMPRESA, producto=PRODUCTO, num_rondas=num_rondas(player.session),
            num_equipos=len(player.group.get_players()), dias_mes=p['dias_mes'],
            stock_inicial=numero(p['stock_inicial']),
            tolerancia=porcentaje(p['tolerancia_pregunta'], 0), puntos_pregunta=p['puntos_pregunta'],
            puntos_resultado=p['puntos_resultado'],
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        texto = (player.nombre_equipo or '').strip()
        if texto:
            player.participant.vars['nombre_equipo'] = texto


class Decision(Page):
    form_model = 'player'
    form_fields = ['lote', 'punto_pedido', 'respuesta']

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Decisión')
        # Propone la política del mes anterior (el equipo la cambia si quiere).
        if player.round_number > 1 and player.field_maybe_none('lote') is None:
            previo = player.in_round(player.round_number - 1)
            player.lote = previo.lote
            player.punto_pedido = previo.punto_pedido
        p = parametros(player.session)
        esc = escenario(player.session)
        mes = player.round_number
        est = estado(player)
        pregunta, _, unidad = modelo.pregunta_del_mes(mes, p, esc)
        return dict(
            empresa=EMPRESA, num_rondas=num_rondas(player.session),
            evento=modelo.EVENTOS[evento_del_mes(player)], texto_evento=texto_evento(mes, p, esc),
            datos=datos_tabla(mes, p, esc),
            stock=numero(est['stock']),
            en_camino=', '.join(f'{numero(u)} unidades el día {max(1, dl + 1)}' for dl, u in est['en_camino']) or 'ninguno',
            pregunta=pregunta, unidad=unidad, pregunta_en_pesos=unidad.startswith('$'),
            tolerancia=porcentaje(p['tolerancia_pregunta'], 0), puntos_pregunta=p['puntos_pregunta'],
            acumulado=pesos(est['costo_acumulado']) if meses_jugados(player) else None,
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        actualizar_tablero(player, 'Esperando a los demás equipos')


class EsperaMes(WaitPage):
    title_text = 'Esperando a los demás equipos'
    body_text = 'El mes se simula cuando todos los equipos hayan enviado su política.'
    after_all_players_arrive = cerrar_mes

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)


class Resultados(Page):
    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Viendo resultados')
        r = meses_jugados(player)[-1]
        p = parametros(player.session)
        preg = r['pregunta']
        rec = r['recomendada']
        return dict(
            empresa=EMPRESA, num_rondas=num_rondas(player.session),
            evento=modelo.EVENTOS[r['evento']],
            lote=numero(r['lote']), punto_pedido=numero(r['punto_pedido']),
            demanda=numero(r['demanda']), vendidas=numero(r['vendidas']), perdidas=numero(r['perdidas']),
            servicio=porcentaje(r['nivel_servicio'], 0), hubo_faltantes=r['perdidas'] > 0,
            stock_inicial=numero(r['stock_inicial']), stock_final=numero(r['stock_final']),
            ordenes=[dict(dia=o['dia'], llega=o['llega'] if o['llega'] <= p['dias_mes'] else f'{o["llega"]} (mes siguiente)',
                          unidades=numero(o['unidades'])) for o in r['ordenes']],
            costos=filas_costos(r), costo=pesos(r['costo']),
            rec_lote=numero(rec['lote']), rec_punto=numero(rec['punto_pedido']), rec_costo=pesos(rec['costo']),
            mejor_que_rec=r['costo'] <= rec['costo'] + 1,
            pregunta=preg['texto'], correcto=texto_valor(preg['correcto'], preg['unidad']),
            respuesta=texto_valor(preg['respuesta'], preg['unidad']), acierto=preg['acierto'],
            puntos_pregunta=p['puntos_pregunta'],
            acumulado=pesos(player.costo_acumulado),
            puesto=puesto(player), num_equipos=len(player.group.get_players()),
        )

    @staticmethod
    def js_vars(player: Player):
        r = meses_jugados(player)[-1]
        return dict(serie=[[x['dia'], x['stock'], x['faltante'], x['llegan']] for x in r['serie']],
                    pedidos=[o['dia'] for o in r['ordenes']], punto_pedido=r['punto_pedido'],
                    stock_inicial=r['stock_inicial'])


class ResultadoFinal(Page):
    @staticmethod
    def is_displayed(player: Player):
        return es_ultima_ronda(player)

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Terminó')
        p = parametros(player.session)
        pts = puntajes(player)
        equipos = sorted(player.group.get_players(), key=lambda q: pts.get(q.id_in_group, 0), reverse=True)
        filas = []
        for i, q in enumerate(equipos):
            e = q.participant.vars.get('estado_deposito') or modelo.estado_inicial(p)
            ms = q.participant.vars.get('meses_deposito', [])
            dem = sum(m['demanda'] for m in ms) or 1
            filas.append(dict(puesto=i + 1, nombre=nombre(q), es_propia=q.id_in_group == player.id_in_group,
                              puntaje=numero(pts.get(q.id_in_group, 0), 1), costo=pesos(e['costo_acumulado']),
                              servicio=porcentaje(sum(m['vendidas'] for m in ms) / dem, 0),
                              preguntas=e['aciertos']))
        est = estado(player)
        meses = meses_jugados(player)
        return dict(
            empresa=EMPRESA, ranking=filas,
            costo=pesos(est['costo_acumulado']),
            costo_recomendado=pesos(sum(m['recomendada']['costo'] for m in meses)),
            aciertos=est['aciertos'], num_meses=len(meses),
            meses=[dict(mes=r['mes'], evento=modelo.EVENTOS[r['evento']],
                        politica=f'n = {numero(r["lote"])} · R = {numero(r["punto_pedido"])}',
                        recomendada=f'n = {numero(r["recomendada"]["lote"])} · R = {numero(r["recomendada"]["punto_pedido"])}',
                        costo=pesos(r['costo']), costo_rec=pesos(r['recomendada']['costo']),
                        servicio=porcentaje(r['nivel_servicio'], 0),
                        pregunta='✓' if r['pregunta']['acierto'] else '✗') for r in meses],
            devolucion=devolucion_de(player),
            comentario_docente=(player.participant.vars.get('comentario_docente') or '').strip(),
            semilla=player.session.vars.get('semilla'),
            puntos_resultado=p['puntos_resultado'],
        )


page_sequence = [Instrucciones, Decision, EsperaMes, Resultados, ResultadoFinal]
