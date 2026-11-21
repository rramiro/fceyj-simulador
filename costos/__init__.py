import random

from otree.api import *

from nucleo import ajustes_otree, tablero, tiempo
from nucleo.formato import numero, pesos, porcentaje

from . import devolucion, modelo

# Página propia para "aula completa" (ver nucleo/ajustes_otree.py).
ajustes_otree.aplicar()


doc = """
Simulador de costos para la gestión (FCEJ - UNLPam).
Cada equipo maneja un taller de cortinas con dos procesos (corte y costura,
embolsado y terminado). Cada mes decide precios y producción de cada línea,
resuelve un evento (pedido especial, comprar o fabricar, nueva línea, eliminar
una línea, equipo alternativo, procesamiento adicional) e informa al empresario
un número calculado. Resultados por costeo variable e integral.
"""

EMPRESA = 'Confecciones del Caldén'
LINEAS = list(modelo.LINEAS)
OPCIONES_BORDADO = [(0, 'No bordar'), (10, '10 %'), (20, '20 %'), (30, '30 %'), (40, '40 %'), (50, '50 %')]
EVENTOS_SI_NO = ('pedido_especial', 'estuches', 'linea_hotel', 'competidor_infantil', 'equipo_embolsado')
PREGUNTA_EVENTO = dict(
    pedido_especial='¿Aceptan el pedido?',
    estuches='¿Empiezan a fabricar los estuches?',
    linea_hotel='¿Lanzan la línea para hoteles (desde el mes que viene)?',
    competidor_infantil='¿Eliminan la línea infantil (desde el mes que viene)?',
    equipo_embolsado='¿Compran el equipo semiautomático?',
)


class C(BaseConstants):
    NAME_IN_URL = 'costos'
    # Todos los equipos frente al mismo escenario y pasando juntos de mes.
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 12
    TITULO_JUEGO = 'Simulador de costos para la gestión'
    SUBTITULO_JUEGO = f'Taller de cortinas «{EMPRESA}»'


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    nombre_equipo = models.StringField(label='Nombre del equipo', max_length=30, blank=True)

    # Decisiones del mes (en pesos y unidades)
    precio_comun = models.FloatField(min=1, label='Precio de la cortina común ($)', blank=True)
    precio_infantil = models.FloatField(min=1, label='Precio de la cortina infantil ($)', blank=True)
    precio_hotel = models.FloatField(min=1, label='Precio de la cortina para hoteles ($)', blank=True)
    prod_comun = models.IntegerField(min=0, max=5000, label='Cortinas comunes a producir', blank=True)
    prod_infantil = models.IntegerField(min=0, max=5000, label='Cortinas infantiles a producir', blank=True)
    prod_hotel = models.IntegerField(min=0, max=5000, label='Cortinas para hoteles a producir', blank=True)
    evento_si = models.BooleanField(choices=[(True, 'Sí'), (False, 'No')], widget=widgets.RadioSelectHorizontal,
                                    label='Decisión', blank=True)
    bordado_pct = models.IntegerField(choices=OPCIONES_BORDADO, label='Parte de las cortinas comunes que se bordan',
                                      blank=True)
    # Puede ser negativa (por ejemplo, la contribución de un pedido por debajo del costo variable).
    informe = models.FloatField(label='Informe al empresario', blank=True, min=-1e12, max=1e12)

    # Resultados del mes
    ventas = models.FloatField()
    contribucion = models.FloatField()
    resultado_var = models.FloatField()
    resultado_int = models.FloatField()
    acumulado_var = models.FloatField()
    acumulado_int = models.FloatField()
    informe_acierto = models.BooleanField()
    puntos_informe = models.IntegerField()
    # No enviaron a tiempo: el plan del mes lo completó el sistema al azar (ver nucleo/tiempo.py).
    fuera_de_tiempo = models.BooleanField(initial=False)


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
    """Estado del taller al empezar el mes (se guarda en participant.vars)."""
    return player.participant.vars.get('estado_costos') or modelo.estado_inicial()


def meses_jugados(player):
    return player.participant.vars.get('meses_costos', [])


def evento_del_mes(player):
    return escenario(player.session)['meses'][player.round_number - 1]['evento']


def decisiones(player):
    est = estado(player)
    precios = {l: player.field_maybe_none(f'precio_{l}') or modelo.LINEAS[l]['precio_ref'] for l in LINEAS}
    produccion = {l: player.field_maybe_none(f'prod_{l}') or 0 for l in est['lineas']}
    tipo = evento_del_mes(player)
    if tipo == 'bordado':
        valor = (player.field_maybe_none('bordado_pct') or 0) / 100
    elif tipo in EVENTOS_SI_NO:
        valor = bool(player.field_maybe_none('evento_si'))
    else:
        valor = None
    return dict(precios=precios, produccion=produccion, evento=valor, informe=player.field_maybe_none('informe'))


def decision_al_azar(player):
    """Plan del mes al azar (cuando el equipo no envía a tiempo): precios cerca del de referencia,
    producción alrededor de la demanda prevista y dentro de la capacidad, evento al azar y sin informe."""
    p = parametros(player.session)
    esc = escenario(player.session)
    est = estado(player)
    tipo = evento_del_mes(player)
    mes = player.round_number
    for l in LINEAS:
        setattr(player, f'precio_{l}', None)
        setattr(player, f'prod_{l}', None)
    acepta = random.random() < 0.5
    prod = {}
    for l in est['lineas']:
        setattr(player, f'precio_{l}', float(round(modelo.LINEAS[l]['precio_ref'] * random.uniform(0.8, 1.2), -2)))
        prod[l] = max(0, int(modelo.demanda_prevista(l, mes, est, p, esc) * random.uniform(0.5, 1.3)))
    pedido = tipo == 'pedido_especial' and acepta
    for _ in range(200):
        if modelo.validar_produccion(prod, est, p, esc, pedido=pedido) is None:
            break
        prod = {l: int(q * 0.9) for l, q in prod.items()}
    for l, q in prod.items():
        setattr(player, f'prod_{l}', q)
    player.evento_si = acepta if tipo in EVENTOS_SI_NO else None
    player.bordado_pct = random.choice([v for v, _ in OPCIONES_BORDADO]) if tipo == 'bordado' else None
    player.informe = None
    player.fuera_de_tiempo = True
    tiempo.marcar_fuera_de_tiempo(player.participant.vars, mes)


def vence_pendiente(player, pagina):
    """Vencimiento de la decisión que el equipo tiene pendiente en esta página (para el tablero)."""
    pv = player.participant.vars
    if pagina in ('Instrucciones', 'Decisión'):
        return tiempo.vencimiento(pv, player.round_number)
    if pagina in ('Resultados listos', 'Viendo resultados') and not es_ultima_ronda(player):
        return tiempo.vencimiento(pv, player.round_number + 1)
    return None


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
    for pl in group.get_players():
        nuevo, r = modelo.simular_mes(pl.round_number, decisiones(pl), estado(pl), p, esc)
        r['fuera_de_tiempo'] = bool(pl.fuera_de_tiempo)
        pl.participant.vars['estado_costos'] = nuevo
        pl.participant.vars['meses_costos'] = meses_jugados(pl) + [r]
        pl.ventas = r['ventas']
        pl.contribucion = r['contribucion']
        pl.resultado_var = r['resultado_var']
        pl.resultado_int = r['resultado_int']
        pl.acumulado_var = nuevo['resultado_var']
        pl.acumulado_int = nuevo['resultado_int']
        pl.informe_acierto = r['informe']['acierto']
        pl.puntos_informe = nuevo['puntos_informe']
    # El reloj del mes siguiente corre desde ahora, igual para todos.
    if group.round_number < num_rondas(group.session):
        tiempo.abrir_ronda([pl.participant.vars for pl in group.get_players()], group.round_number + 1,
                           group.session.config)
    for pl in group.get_players():
        actualizar_tablero(pl, 'Resultados listos')


def puntajes(player):
    """Puntaje de cada equipo del grupo con los resultados acumulados hasta ahora: {id_in_group: puntos}."""
    equipos = [q for q in player.group.get_players() if q.participant.vars.get('estado_costos')]
    if not equipos:
        return {}
    ests = [q.participant.vars['estado_costos'] for q in equipos]
    pts = modelo.puntaje_final([e['resultado_var'] for e in ests], [e['puntos_informe'] for e in ests],
                               parametros(player.session))
    return {q.id_in_group: x for q, x in zip(equipos, pts)}


def puesto(player):
    pts = puntajes(player)
    if player.id_in_group not in pts:
        return None
    orden = sorted(pts, key=pts.get, reverse=True)
    return orden.index(player.id_in_group) + 1


# --- Datos para las pantallas ----------------------------------------------------------

def hoja_especificaciones(player):
    """Datos técnicos de cada línea activa (el costo variable lo calculan los equipos)."""
    p = parametros(player.session)
    est = estado(player)
    esc = escenario(player.session)
    filas = []
    for l in LINEAS:
        if l not in est['lineas'] and not (l == 'hotel' and evento_del_mes(player) == 'linea_hotel'):
            continue
        d = modelo.LINEAS[l]
        filas.append(dict(
            linea=d['nombre'], activa=l in est['lineas'],
            tela=numero(d['tela_m'], 1), accesorios=pesos(d['accesorios']),
            horas_corte=numero(d['horas_corte'], 2),
            horas_embolsado=numero(modelo.horas_embolsado(l, est, esc), 2),
            comision=porcentaje(d['comision'], 0), precio_ref=pesos(d['precio_ref']),
            cf_directos=pesos(modelo.cf_directos(l, esc)),
            demanda=numero(modelo.demanda_prevista(l, player.round_number, est, p, esc)),
            elasticidad=numero(d['elasticidad'], 1),
            stock=numero(est['stock'][l]),
        ))
    return filas


def texto_evento(player):
    """Descripción del evento del mes con sus datos."""
    tipo = evento_del_mes(player)
    ev = escenario(player.session)['eventos']
    p = parametros(player.session)
    est = estado(player)
    if tipo == 'pedido_especial':
        e = ev['pedido_especial']
        return (f'La organización de la Expopymes pide {e["unidades"]} cortinas comunes con su logo bordado, a '
                f'{pesos(e["precio"])} cada una. El bordado lo hace un tercero a {pesos(e["bordado"])} por cortina. '
                f'Si con su plan no alcanzan las horas de corte, pueden contratar hasta {e["horas_extra"]} horas extra, '
                f'con un costo fijo de {pesos(e["cf_horas_extra"])} en el mes. El pedido se produce y se entrega este mes.')
    if tipo == 'estuches':
        e = ev['estuches']
        return (f'Hoy compran los estuches a {pesos(p["estuche_compra"])}. Podrían fabricarlos: costo fijo de '
                f'{pesos(e["cf"])} por mes y costo variable de {pesos(e["cv_propio"])} por estuche. Si deciden fabricar, '
                'rige desde este mes y para el resto del juego.')
    if tipo == 'linea_hotel':
        e = ev['linea_hotel']
        return (f'La Asociación de Hoteleros ofrece una línea de cortinas para hoteles: precio de referencia '
                f'{pesos(modelo.LINEAS["hotel"]["precio_ref"])}, demanda prevista de unas {e["demanda"]} cortinas por mes '
                f'a ese precio y costos fijos propios de {pesos(e["cf"])} por mes. Los datos técnicos están en la hoja de '
                'especificaciones. Si la lanzan, empieza el mes que viene.')
    if tipo == 'competidor_infantil':
        e = ev['competidor_infantil']
        d = modelo.LINEAS['infantil']
        return (f'Se instaló un competidor: desde este mes, la demanda de cortinas infantiles cae al '
                f'{porcentaje(e["factor"], 0)} de lo normal. Los costos fijos directos de la línea son '
                f'{pesos(d["cf_directos"])}, de los cuales {pesos(d["cf_evitables"])} son evitables si la cierran. '
                'Si la eliminan, deja de producirse desde el mes que viene.')
    if tipo == 'equipo_embolsado':
        e = ev['equipo_embolsado']
        return (f'Un equipo de embolsado semiautomático: costo fijo de {pesos(e["cf"])} por mes, '
                f'{numero(e["horas"], 2)} horas máquina por cortina a {pesos(e["cv_hora"])} la hora. Hoy: '
                f'{numero(modelo.LINEAS["comun"]["horas_embolsado"], 2)} horas a {pesos(p["cv_hora_embolsado"])}. '
                'Si lo compran, rige desde este mes.')
    if tipo == 'bordado':
        e = ev['bordado']
        return (f'Pueden bordar parte de las cortinas comunes (modelo premium): {pesos(e["precio_extra"])} más en el '
                f'precio y {pesos(e["cv_extra"])} más de costo variable por cortina, con un costo fijo de '
                f'{pesos(e["cf"])} por mes mientras lo hagan. Lo que elijan rige desde este mes.')
    if tipo == 'suba_tela':
        e = ev['suba_tela']
        return (f'El proveedor sube la tela un {porcentaje(e["suba"], 0)} desde este mes. El costo estándar sigue en '
                f'{pesos(p["precio_tela"])} el metro: la suba aparece como desvío de precio.')
    return 'Este mes no hay novedades.'


def filas_resultados(r):
    return [dict(linea=f['nombre'], precio=pesos(f['precio']), produccion=numero(f['produccion']),
                 demanda=numero(f['demanda']), vendidas=numero(f['vendidas']), faltante=numero(f['faltante']),
                 hubo_faltante=f['faltante'] > 0.5, stock=numero(f['stock_final']),
                 cv=pesos(f['cv_unitario']), cf=pesos(f['cf_unitario']), cm=pesos(f['contribucion_unitaria']))
            for f in r['filas'].values()]


def estado_resultados(r):
    """Estado de resultados del mes por costeo variable e integral, lado a lado."""
    cf = r['costos_fijos']
    desvios = sum(r['desvios'].values())
    otros_cf = r['cf_total'] - cf['produccion']
    return dict(
        ventas=pesos(r['ventas']),
        cv_ventas=pesos(r['cv_ventas']), costo_ventas_int=pesos(r['costo_ventas_int']),
        comisiones=pesos(r['comisiones']),
        contribucion=pesos(r['contribucion']),
        bruto_int=pesos(r['ventas'] - r['costo_ventas_int'] - r['comisiones']),
        desvios=pesos(desvios), desvios_neg=desvios > 0,
        cf_produccion=pesos(cf['produccion']),
        variacion_capacidad=pesos(r['variacion_capacidad']), subaplicacion=r['variacion_capacidad'] > 0,
        otros_cf=pesos(otros_cf),
        resultado_var=pesos(r['resultado_var']), resultado_var_neg=r['resultado_var'] < 0,
        resultado_int=pesos(r['resultado_int']), resultado_int_neg=r['resultado_int'] < 0,
        desvio_precio=pesos(r['desvios']['precio_tela']), desvio_consumo=pesos(r['desvios']['consumo_tela']),
        desvio_eficiencia=pesos(r['desvios']['eficiencia_mo']),
        cf_aplicados=pesos(r['cf_aplicados']),
        detalle_cf=[dict(concepto=k, monto=pesos(v)) for k, v in
                    (('Producción (CFC + CFO de los dos procesos)', cf['produccion']),
                     ('Administración', cf['administracion']), ('Comercialización', cf['comercializacion']),
                     ('Directos de las líneas', cf['directos']), ('Fabricación de estuches', cf['estuches']),
                     ('Equipo semiautomático', cf['equipo']), ('Bordado', cf['bordado']),
                     ('Horas extra', cf['horas_extra'])) if v],
    )


def texto_valor(valor, unidad):
    if valor is None:
        return '—'
    return pesos(valor) if unidad == '$' else f'{numero(valor)} {unidad}'


def texto_decision(tipo, valor):
    if tipo == 'bordado':
        return f'bordar {porcentaje(valor or 0, 0)}'
    if tipo in EVENTOS_SI_NO:
        return 'sí' if valor else 'no'
    return '—'


# --- Tablero del docente y devolución ------------------------------------------------------

ETAPAS_TABLERO = {
    'Instrucciones': ('decidiendo', 'Leyendo instrucciones'),
    'Decisión': ('decidiendo', 'Decidiendo'),
    'Esperando a los demás equipos': ('esperando', 'Decisión enviada'),
    'Resultados listos': ('resultados', 'Resultados listos'),
    'Viendo resultados': ('resultados', 'Viendo resultados'),
    'Terminó': ('termino', 'Terminó'),
}

COLUMNAS_TABLERO = [
    tablero.columna('mes', 'M', 'ronda'),
    tablero.columna('evento', 'Evento', 'texto'),
    tablero.columna('decision', 'Decidió', 'texto'),
    tablero.columna('ventas', 'Ventas', 'pesos'),
    tablero.columna('resultado_var', 'Res. variable', 'pesos', signo=True),
    tablero.columna('resultado_int', 'Res. integral', 'pesos', signo=True),
    tablero.columna('informe', 'Informe', 'texto'),
    tablero.columna('envio', 'Envío', 'texto'),
]


def historial(player):
    return [dict(mes=r['mes'], evento=modelo.NOMBRES_EVENTO[r['evento']],
                 decision=texto_decision(r['evento'], r['decision']), ventas=r['ventas'],
                 resultado_var=r['resultado_var'], resultado_int=r['resultado_int'],
                 informe='✓' if r['informe']['acierto'] else '✗',
                 envio='⏱ al azar' if r.get('fuera_de_tiempo') else 'a tiempo')
            for r in meses_jugados(player)]


def devolucion_de(player):
    meses = meses_jugados(player)
    if not meses:
        return []
    est = estado(player)
    return devolucion.diagnosticar(meses, est, parametros(player.session), puesto(player),
                                   len(player.group.get_players()),
                                   terminado=len(meses) == num_rondas(player.session))


def actualizar_tablero(player, pagina):
    etapa, estado_txt = ETAPAS_TABLERO[pagina]
    est = estado(player)
    pts = puntajes(player)
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
            tablero.indicador('Res. acumulado', est['resultado_var'] if meses_jugados(player) else None, 'pesos', signo=True),
            tablero.indicador('Informes', est['puntos_informe'] if meses_jugados(player) else None, 'numero'),
            tablero.indicador('Puntaje', numero(pts[player.id_in_group], 1) if player.id_in_group in pts else None, 'texto'),
        ],
        decision=None,
        columnas=COLUMNAS_TABLERO,
        filas=historial(player),
        nota_historial='Resultados del mes; el ranking usa el resultado acumulado por costeo variable.',
        devolucion=devolucion_de(player),
        vence=vence_pendiente(player, pagina),
        fuera_de_tiempo=tiempo.rondas_fuera_de_tiempo(player.participant.vars),
    )


def aviso_tiempo(session):
    """Minutos por mes en texto para las pantallas (None si no hay límite)."""
    if not tiempo.hay_limite(session.config):
        return None
    return tiempo.texto_minutos(tiempo.minutos_por_ronda(session.config))


# --- Páginas --------------------------------------------------------------------------

class Instrucciones(Page):
    form_model = 'player'
    form_fields = ['nombre_equipo']
    timer_text = tiempo.TEXTO_DECISION

    @staticmethod
    def get_timeout_seconds(player: Player):
        return tiempo.segundos_restantes(tiempo.iniciar_primera_ronda(player.participant.vars, player.session.config))

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def vars_for_template(player: Player):
        tiempo.iniciar_primera_ronda(player.participant.vars, player.session.config)
        actualizar_tablero(player, 'Instrucciones')
        p = parametros(player.session)
        return dict(
            empresa=EMPRESA, num_rondas=num_rondas(player.session),
            num_equipos=len(player.group.get_players()),
            precio_tela=pesos(p['precio_tela']), rendimiento=porcentaje(p['rendimiento_tela'], 0),
            costo_hora_mo=pesos(p['costo_hora_mo']), tasa_cv_corte=pesos(p['tasa_cv_corte']),
            cv_hora_embolsado=pesos(p['cv_hora_embolsado']), estuche=pesos(p['estuche_compra']),
            cm_corte=numero(p['cm_corte']), np_corte=numero(p['np_corte']),
            cfc_corte=pesos(p['cfc_corte']), cfo_corte=pesos(p['cfo_corte']),
            tasa_corte=pesos(modelo.tasa_corte(p)),
            cm_embolsado=numero(p['cm_embolsado']), np_embolsado=numero(p['np_embolsado']),
            cfc_embolsado=pesos(p['cfc_embolsado']), cfo_embolsado=pesos(p['cfo_embolsado']),
            tasa_embolsado=pesos(modelo.tasa_embolsado(p)),
            cf_administracion=pesos(p['cf_administracion']), cf_comercializacion=pesos(p['cf_comercializacion']),
            tolerancia=porcentaje(p['tolerancia_informe'], 0), puntos_informe=p['puntos_informe'],
            puntos_resultado=p['puntos_resultado'],
            minutos=aviso_tiempo(player.session),
            minutos_primera=tiempo.texto_minutos(tiempo.minutos_primera_ronda(player.session.config)),
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        texto = (player.nombre_equipo or '').strip()
        if texto:
            player.participant.vars['nombre_equipo'] = texto


class Decision(Page):
    form_model = 'player'
    timer_text = tiempo.TEXTO_DECISION

    @staticmethod
    def get_timeout_seconds(player: Player):
        pv = player.participant.vars
        if player.round_number == 1:
            tiempo.iniciar_primera_ronda(pv, player.session.config)
        return tiempo.segundos_restantes(tiempo.vencimiento(pv, player.round_number))

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)

    @staticmethod
    def get_form_fields(player: Player):
        est = estado(player)
        campos = []
        for l in est['lineas']:
            campos += [f'precio_{l}', f'prod_{l}']
        tipo = evento_del_mes(player)
        if tipo == 'bordado':
            campos.append('bordado_pct')
        elif tipo in EVENTOS_SI_NO:
            campos.append('evento_si')
        return campos + ['informe']

    @staticmethod
    def error_message(player: Player, valores):
        est = estado(player)
        for l in est['lineas']:
            if valores.get(f'precio_{l}') is None or valores.get(f'prod_{l}') is None:
                return 'Completen el precio y la producción de cada línea.'
        tipo = evento_del_mes(player)
        if tipo in EVENTOS_SI_NO and valores.get('evento_si') is None:
            return 'Respondan la decisión del evento del mes.'
        produccion = {l: valores[f'prod_{l}'] for l in est['lineas']}
        pedido = tipo == 'pedido_especial' and bool(valores.get('evento_si'))
        return modelo.validar_produccion(produccion, est, parametros(player.session), escenario(player.session), pedido)

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Decisión')
        p = parametros(player.session)
        esc = escenario(player.session)
        est = estado(player)
        tipo = evento_del_mes(player)
        pregunta, _, unidad = modelo.informe_correcto(tipo, None, player.round_number, est, p, esc)
        anteriores = meses_jugados(player)
        ultimo = anteriores[-1] if anteriores else None
        return dict(
            empresa=EMPRESA, num_rondas=num_rondas(player.session),
            evento=modelo.NOMBRES_EVENTO[tipo], texto_evento=texto_evento(player),
            pregunta_evento=PREGUNTA_EVENTO.get(tipo), es_bordado=tipo == 'bordado',
            pregunta_informe=pregunta, unidad_informe=unidad, informe_en_pesos=unidad.startswith('$'),
            tolerancia_informe=porcentaje(p['tolerancia_informe'], 0), puntos_informe=p['puntos_informe'],
            hoja=hoja_especificaciones(player),
            lineas=est['lineas'],
            hay_comun='comun' in est['lineas'], hay_infantil='infantil' in est['lineas'],
            hay_hotel='hotel' in est['lineas'],
            cm_corte=numero(p['cm_corte']), cm_embolsado=numero(p['cm_embolsado']),
            costos_fijos=pesos(sum(modelo.costos_fijos_periodo(est, p, esc).values())),
            precio_tela=pesos(p['precio_tela']), rendimiento=porcentaje(p['rendimiento_tela'], 0),
            fabrica_estuches=est['fabrica_estuches'], equipo=est['equipo_semiautomatico'],
            bordado=porcentaje(est['bordado'], 0) if est['bordado'] else None,
            acumulado=pesos(est['resultado_var']) if anteriores else None,
            ultimo_cv=' · '.join(f"{f['nombre']} {pesos(f['cv_unitario'])}" for f in ultimo['filas'].values()) if ultimo else None,
            minutos=aviso_tiempo(player.session),
        )

    @staticmethod
    def js_vars(player: Player):
        est = estado(player)
        esc = escenario(player.session)
        p = parametros(player.session)
        return dict(
            horas={l: [modelo.LINEAS[l]['horas_corte'], modelo.horas_embolsado(l, est, esc)] for l in est['lineas']},
            cm=[p['cm_corte'], p['cm_embolsado']],
            pedido=[esc['eventos']['pedido_especial']['unidades'] * modelo.LINEAS['comun']['horas_corte'],
                    esc['eventos']['pedido_especial']['unidades'] * modelo.horas_embolsado('comun', est, esc)]
            if evento_del_mes(player) == 'pedido_especial' else [0, 0],
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        if timeout_happened:
            decision_al_azar(player)
        actualizar_tablero(player, 'Esperando a los demás equipos')


class EsperaMes(WaitPage):
    title_text = 'Esperando a los demás equipos'
    body_text = 'El mes se cierra cuando todos los equipos hayan enviado su plan.'
    after_all_players_arrive = cerrar_mes

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)


class Resultados(Page):
    timer_text = tiempo.TEXTO_LECTURA

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)

    @staticmethod
    def get_timeout_seconds(player: Player):
        # El reloj del mes siguiente ya corre mientras leen los resultados.
        if es_ultima_ronda(player):
            return None
        return tiempo.segundos_restantes(tiempo.vencimiento(player.participant.vars, player.round_number + 1))

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Viendo resultados')
        r = meses_jugados(player)[-1]
        p = parametros(player.session)
        inf = r['informe']
        return dict(
            empresa=EMPRESA, num_rondas=num_rondas(player.session),
            evento=modelo.NOMBRES_EVENTO[r['evento']],
            decision=texto_decision(r['evento'], r['decision']),
            recomendada=texto_decision(r['evento'], r['recomendada']) if r['recomendada'] is not None else None,
            decidio_bien=r['recomendada'] is None or texto_decision(r['evento'], r['decision'])
            == texto_decision(r['evento'], r['recomendada']),
            filas=filas_resultados(r),
            pedido=r['pedido'], horas_extra=r['horas_extra'],
            er=estado_resultados(r),
            horas_corte=numero(r['horas_corte']), horas_embolsado=numero(r['horas_embolsado']),
            cm_corte=numero(p['cm_corte']), cm_embolsado=numero(p['cm_embolsado']),
            ociosidad_corte=porcentaje(r['ociosidad_corte'], 0), ociosidad_embolsado=porcentaje(r['ociosidad_embolsado'], 0),
            pe=numero(r['punto_equilibrio']) if r['punto_equilibrio'] else '—',
            ms=porcentaje(r['margen_seguridad'], 0) if r['margen_seguridad'] is not None else '—',
            ms_neg=(r['margen_seguridad'] or 0) < 0,
            informe_pregunta=inf['pregunta'], informe_correcto=texto_valor(inf['correcto'], inf['unidad']),
            informe_respuesta=texto_valor(inf['respuesta'], inf['unidad']) if inf['respuesta'] is not None else 'sin respuesta',
            informe_acierto=inf['acierto'], puntos_informe=p['puntos_informe'],
            acumulado_var=pesos(player.acumulado_var), acumulado_int=pesos(player.acumulado_int),
            puesto=puesto(player), num_equipos=len(player.group.get_players()),
            stock_var=pesos(r['stock_var']), stock_int=pesos(r['stock_int']),
            fuera_de_tiempo=r.get('fuera_de_tiempo', False),
        )


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
            e = q.participant.vars.get('estado_costos') or modelo.estado_inicial()
            filas.append(dict(puesto=i + 1, nombre=nombre(q), es_propia=q.id_in_group == player.id_in_group,
                              puntaje=numero(pts.get(q.id_in_group, 0), 1), resultado=pesos(e['resultado_var']),
                              negativo=e['resultado_var'] < 0, integral=pesos(e['resultado_int']),
                              informes=e['puntos_informe']))
        est = estado(player)
        meses = meses_jugados(player)
        return dict(
            empresa=EMPRESA, ranking=filas,
            acumulado_var=pesos(est['resultado_var']), acumulado_int=pesos(est['resultado_int']),
            diferencia=pesos(est['resultado_int'] - est['resultado_var']),
            aciertos=sum(1 for r in meses if r['informe']['acierto']), num_meses=len(meses),
            meses=[dict(mes=r['mes'], evento=modelo.NOMBRES_EVENTO[r['evento']],
                        decision=texto_decision(r['evento'], r['decision']),
                        recomendada=texto_decision(r['evento'], r['recomendada']) if r['recomendada'] is not None else '—',
                        resultado=pesos(r['resultado_var']), negativo=r['resultado_var'] < 0,
                        informe='✓' if r['informe']['acierto'] else '✗',
                        fuera_de_tiempo=r.get('fuera_de_tiempo', False)) for r in meses],
            devolucion=devolucion_de(player),
            comentario_docente=(player.participant.vars.get('comentario_docente') or '').strip(),
            semilla=player.session.vars.get('semilla'),
            puntos_resultado=parametros(player.session)['puntos_resultado'],
            fuera_de_tiempo=', '.join(str(r['mes']) for r in meses if r.get('fuera_de_tiempo')),
        )


page_sequence = [Instrucciones, Decision, EsperaMes, Resultados, ResultadoFinal]
