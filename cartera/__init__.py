import random

from otree.api import *

from nucleo import ajustes_otree, tablero
from nucleo.formato import numero, pesos, porcentaje

from . import devolucion, modelo

# Página propia para "aula completa" (ver nucleo/ajustes_otree.py).
ajustes_otree.aplicar()


doc = """
Simulador de cartera de inversión (FCEJ - UNLPam).
Cada equipo administra una cartera durante varios trimestres y, en cada uno,
reparte su dinero entre acciones internacionales, bonos de renta fija y
liquidez. Todos los equipos enfrentan el mismo escenario de mercado, con
inflación y tipo de cambio; cada año se evalúa la rentabilidad real.
"""

COLOR_PROPIO = '#2F2E70'
COLORES_REFERENCIAS = ['#3B9AD7', '#9AA5B1', '#C9A227']

NOMBRES_ACTIVOS = dict(acciones='Acciones internacionales', bonos='Bonos de renta fija', liquidez='Liquidez (plazo fijo)')

# Titulares del trimestre: anticipan (con error) cómo les irá a las acciones.
TITULARES = dict(
    optimista=[
        'Wall Street: los analistas esperan un buen trimestre para las grandes empresas',
        'Mejoran las perspectivas de la economía mundial y suben los pronósticos de ganancias',
        'Baja la incertidumbre global: los inversores vuelven a buscar acciones',
        'Las tecnológicas anticipan resultados mejores que los esperados',
        'Los bancos centrales dan señales de calma y los mercados lo celebran',
        'Fuerte demanda de acciones en los mercados internacionales',
    ],
    pesimista=[
        'Crecen los temores de una desaceleración de la economía mundial',
        'Tensión internacional: los inversores buscan refugio y se alejan del riesgo',
        'Advierten que las acciones están caras y podría haber una corrección',
        'Las empresas recortan sus pronósticos de ganancias para el trimestre',
        'Suben las tasas en el mundo y presionan a la baja a las bolsas',
        'Volatilidad en los mercados: los analistas recomiendan prudencia',
    ],
)


class C(BaseConstants):
    NAME_IN_URL = 'cartera'
    # Todos los equipos de la sesión juegan juntos: enfrentan el mismo escenario y
    # pasan juntos de trimestre (así nadie puede contarles el futuro a los demás).
    PLAYERS_PER_GROUP = None
    # Máximo de trimestres (4 años). La cantidad efectiva es 'num_rondas' de la configuración.
    NUM_ROUNDS = 16
    # Nombre del juego en el encabezado de las pantallas (_templates/global/encabezado.html).
    TITULO_JUEGO = 'Simulador de inversiones'
    SUBTITULO_JUEGO = 'Cartera: acciones, bonos y liquidez'


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    # Escenario del trimestre (igual para todos; sorteado al crear la sesión)
    inflacion = models.FloatField()
    indice = models.FloatField()          # índice de precios al cerrar el trimestre (1 = inicio del juego)
    var_dolar = models.FloatField()       # variación del dólar en el trimestre
    dolar = models.FloatField()           # índice del dólar al cerrar el trimestre (1 = inicio)
    rend_acciones = models.FloatField()   # rendimientos nominales en pesos del trimestre
    rend_bonos = models.FloatField()
    rend_liquidez = models.FloatField()
    acciones_usd = models.FloatField()    # rendimiento de las acciones en dólares
    crisis = models.BooleanField()
    noticia = models.StringField()        # 'optimista' | 'pesimista'


class Player(BasePlayer):
    nombre_equipo = models.StringField(label='Nombre del equipo', max_length=30, blank=True)

    # Decisión: porcentaje de la cartera en cada activo (suman 100, en pasos de 5)
    pct_acciones = models.IntegerField(min=0, max=100, label='Acciones internacionales (%)')
    pct_bonos = models.IntegerField(min=0, max=100, label='Bonos de renta fija (%)')
    pct_liquidez = models.IntegerField(min=0, max=100, label='Liquidez (%)')

    # Resultados del trimestre (en pesos de cada trimestre)
    valor_inicial = models.FloatField()
    comision = models.FloatField()
    monto_acciones = models.FloatField()   # al cerrar el trimestre
    monto_bonos = models.FloatField()
    monto_liquidez = models.FloatField()
    valor_final = models.FloatField()
    rendimiento = models.FloatField()       # nominal del trimestre
    rendimiento_real = models.FloatField()
    valor_real = models.FloatField()        # en pesos del inicio del juego
    valor_dolares = models.FloatField()     # en "dólares del inicio": valor / índice del dólar


# --- Funciones auxiliares ---------------------------------------------------

def num_rondas(session):
    return min(session.config.get('num_rondas', 12), C.NUM_ROUNDS)


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


def anterior(player):
    return player.in_round(player.round_number - 1) if player.round_number > 1 else None


def pesos_decididos(player):
    return (player.pct_acciones / 100, player.pct_bonos / 100, player.pct_liquidez / 100)


def montos_al_empezar(player):
    """Lo que hay en cada activo al empezar el trimestre (al empezar el juego, todo en liquidez)."""
    ant = anterior(player)
    if ant is None:
        return [0.0, 0.0, float(player.session.config['capital_inicial'])]
    return [ant.monto_acciones, ant.monto_bonos, ant.monto_liquidez]


def texto_anios(trimestres):
    anios = trimestres / 4
    return '1 año' if trimestres == 4 else f'{numero(anios, 0 if trimestres % 4 == 0 else 1)} años'


def texto_parcial(trimestres):
    """'' si el año está completo; si no, '2 trimestres'."""
    if trimestres == 4:
        return ''
    return '1 trimestre' if trimestres == 1 else f'{trimestres} trimestres'


def anio_de(ronda):
    return (ronda - 1) // 4 + 1


def rondas_jugadas(player):
    """Rondas de este jugador que ya tienen resultados calculados."""
    return [p for p in player.in_rounds(1, player.round_number)
            if p.field_maybe_none('valor_final') is not None]


def filas_modelo(player):
    """Las rondas jugadas en el formato de modelo.evaluar()."""
    return [dict(trimestre=p.round_number, pesos=pesos_decididos(p), comision=p.comision,
                 valor_final=p.valor_final, valor_real=p.valor_real, valor_dolares=p.valor_dolares,
                 rendimiento=p.rendimiento, rendimiento_real=p.rendimiento_real)
            for p in rondas_jugadas(player)]


def evaluacion(player):
    filas = filas_modelo(player)
    if not filas:
        return None
    return modelo.evaluar(filas, escenario(player.session)[:len(filas)], parametros(player.session))


def referencias(session, trimestres):
    """Carteras de referencia en el escenario de la sesión hasta `trimestres`."""
    esc = escenario(session)[:trimestres]
    params = parametros(session)
    salida = {}
    for nombre_ref, pesos_ref in modelo.REFERENCIAS.items():
        filas = modelo.simular_cartera([pesos_ref] * len(esc), esc, params)
        salida[nombre_ref] = dict(filas=filas, evaluacion=modelo.evaluar(filas, esc, params))
    return salida


def ranking(player, clave='valor_real'):
    """Equipos ordenados por valor real (= por TEA real) o por Sharpe, en la última ronda con resultados."""
    jugadas = rondas_jugadas(player)
    if not jugadas:
        return []
    r = jugadas[-1].round_number
    equipos = [p.in_round(r) for p in player.group.get_players()]
    if clave == 'sharpe':
        valores = {p.id_in_group: evaluacion(p)['sharpe'] for p in equipos}
        return sorted(equipos, key=lambda p: valores[p.id_in_group], reverse=True), valores
    return sorted(equipos, key=lambda p: p.valor_real, reverse=True), {p.id_in_group: p.valor_real for p in equipos}


def puesto(player, clave='valor_real'):
    orden = ranking(player, clave)
    if not orden:
        return None
    return [p.id_in_group for p in orden[0]].index(player.id_in_group) + 1


# --- Creación de la sesión: el escenario de mercado ----------------------------

def creating_session(subsession: Subsession):
    session = subsession.session
    cfg = session.config
    if subsession.round_number == 1:
        semilla = int(cfg.get('semilla') or 0) or random.randint(1, 999_999)
        session.vars['semilla'] = semilla
        session.vars['escenario'] = modelo.generar_escenario(parametros(session), num_rondas(session), semilla)
    r = subsession.round_number
    if r > num_rondas(session):
        return
    d = escenario(session)[r - 1]
    for g in subsession.get_groups():
        g.inflacion = d['inflacion']
        g.indice = d['indice']
        g.var_dolar = d['var_dolar']
        g.dolar = d['dolar']
        g.rend_acciones = d['rendimientos']['acciones']
        g.rend_bonos = d['rendimientos']['bonos']
        g.rend_liquidez = d['rendimientos']['liquidez']
        g.acciones_usd = d['acciones_usd']
        g.crisis = d['crisis']
        g.noticia = d['noticia']
    # Propuesta inicial de la primera decisión: todo en liquidez (como empieza la cartera).
    # Las siguientes se proponen al cerrar cada trimestre (ver calcular_resultados).
    if r == 1:
        for p in subsession.get_players():
            p.pct_acciones, p.pct_bonos, p.pct_liquidez = 0, 0, 100


# --- Cálculo de resultados ----------------------------------------------------

def calcular_resultados(group: Group):
    session = group.session
    datos = escenario(session)[group.round_number - 1]
    comision = session.config['comision']
    for p in group.get_players():
        r = modelo.simular_trimestre(montos_al_empezar(p), pesos_decididos(p), datos, comision)
        p.valor_inicial = r['valor_inicial']
        p.comision = r['comision']
        p.monto_acciones, p.monto_bonos, p.monto_liquidez = r['montos']
        p.valor_final = r['valor_final']
        p.rendimiento = r['rendimiento']
        p.rendimiento_real = (1 + r['rendimiento']) / (1 + datos['inflacion']) - 1
        p.valor_real = r['valor_final'] / datos['indice']
        p.valor_dolares = r['valor_final'] / datos['dolar']
        # El trimestre siguiente propone el mismo reparto (oTree arma el formulario con estos valores).
        if group.round_number < num_rondas(session):
            siguiente = p.in_round(group.round_number + 1)
            siguiente.pct_acciones, siguiente.pct_bonos, siguiente.pct_liquidez = (
                p.pct_acciones, p.pct_bonos, p.pct_liquidez)
    # Recién con todos los valores se puede calcular el puesto de cada uno.
    for p in group.get_players():
        actualizar_tablero(p, 'Resultados listos')


# --- Datos para las pantallas -----------------------------------------------------

def titular(group: Group):
    lista = TITULARES[group.noticia]
    return lista[(group.round_number - 1) % len(lista)]


def tabla_rendimientos(player, hasta):
    """Rendimientos nominales de cada activo, inflación y dólar en los trimestres 1..hasta (públicos)."""
    filas = []
    for r in range(1, hasta + 1):
        g = player.group.in_round(r)
        filas.append(dict(
            trimestre=f'T{r}', crisis=g.crisis,
            inflacion=porcentaje(g.inflacion), dolar=porcentaje(g.var_dolar),
            acciones=porcentaje(g.rend_acciones), acciones_usd=porcentaje(g.acciones_usd),
            bonos=porcentaje(g.rend_bonos), liquidez=porcentaje(g.rend_liquidez),
            acciones_neg=g.rend_acciones < 0, bonos_neg=g.rend_bonos < 0,
        ))
    return filas


def composicion(montos):
    total = sum(montos) or 1
    return [dict(activo=NOMBRES_ACTIVOS[a], monto=pesos(m), pct=porcentaje(m / total, 0))
            for a, m in zip(modelo.ACTIVOS, montos)]


def datos_graficos(player):
    """Valor real de la cartera propia y de las de referencia, trimestre a trimestre (en millones)."""
    jugadas = rondas_jugadas(player)
    n = len(jugadas)
    capital = player.session.config['capital_inicial']
    etiquetas = ['Inicio'] + [f'T{p.round_number}' for p in jugadas]
    series = [dict(nombre=f'{nombre(player)} (ustedes)', valores=[capital] + [p.valor_real for p in jugadas],
                   color=COLOR_PROPIO, ancho=3)]
    for k, (nombre_ref, ref) in enumerate(referencias(player.session, n).items()):
        series.append(dict(nombre=nombre_ref, valores=[capital] + [f['valor_real'] for f in ref['filas']],
                           color=COLORES_REFERENCIAS[k % len(COLORES_REFERENCIAS)], punteada=True))
    return dict(etiquetas=etiquetas, series=series)


def filas_ranking(player, clave):
    orden, valores = ranking(player, clave)
    capital = player.session.config['capital_inicial']
    n = len(rondas_jugadas(player))
    filas = []
    for i, p in enumerate(orden):
        fila = dict(puesto=i + 1, nombre=nombre(p), es_propia=p.id_in_group == player.id_in_group)
        if clave == 'sharpe':
            fila.update(valor=numero(valores[p.id_in_group], 2), negativo=valores[p.id_in_group] < 0)
        else:
            t = modelo.tea(p.valor_real, capital, n)
            fila.update(valor=porcentaje(t), negativo=t < 0, valor_real=pesos(p.valor_real))
        filas.append(fila)
    return filas


def indicadores(ev):
    return dict(
        tea_real=porcentaje(ev['tea_real']), tea_real_neg=ev['tea_real'] < 0,
        tea_dolares=porcentaje(ev['tea_dolares']), tea_dolares_neg=ev['tea_dolares'] < 0,
        volatilidad=porcentaje(ev['volatilidad']), sharpe=numero(ev['sharpe'], 2),
        caida_maxima=porcentaje(ev['caida_maxima']), comisiones=pesos(ev['comisiones']),
    )


# --- Tablero del docente y devolución -----------------------------------------------

ETAPAS_TABLERO = {
    'Instrucciones': ('decidiendo', 'Leyendo instrucciones'),
    'Decisión': ('decidiendo', 'Decidiendo'),
    'Esperando a los demás equipos': ('esperando', 'Decisión enviada'),
    'Resultados listos': ('resultados', 'Resultados listos'),
    'Viendo resultados': ('resultados', 'Viendo resultados'),
    'Informe anual': ('resultados', 'Informe anual'),
    'Terminó': ('termino', 'Terminó'),
}

COLUMNAS_TABLERO = [
    tablero.columna('trimestre', 'T', 'ronda'),
    tablero.columna('acciones', 'Acciones', 'pct'),
    tablero.columna('bonos', 'Bonos', 'pct'),
    tablero.columna('liquidez', 'Liquidez', 'pct'),
    tablero.columna('rendimiento_real', 'Rend. real', 'pct1', signo=True),
    tablero.columna('comision', 'Comisión', 'pesos'),
    tablero.columna('valor_final', 'Valor', 'pesos'),
    tablero.columna('valor_real', 'Valor real', 'pesos', signo=False),
]


def historial(player):
    """Datos por trimestre para la devolución y el tablero."""
    filas = []
    for p in rondas_jugadas(player):
        g = p.group
        filas.append(dict(
            trimestre=p.round_number,
            acciones=p.pct_acciones / 100, bonos=p.pct_bonos / 100, liquidez=p.pct_liquidez / 100,
            rendimiento=p.rendimiento, rendimiento_real=p.rendimiento_real,
            comision=p.comision, valor_inicial=p.valor_inicial, valor_final=p.valor_final,
            valor_real=p.valor_real, valor_dolares=p.valor_dolares,
            crisis=g.crisis, noticia=g.noticia, inflacion=g.inflacion,
            rend_acciones=g.rend_acciones, rend_bonos=g.rend_bonos, rend_liquidez=g.rend_liquidez,
        ))
    return filas


def devolucion_de(player):
    filas = historial(player)
    if not filas:
        return []
    n = len(filas)
    ev = evaluacion(player)
    refs = {k: v['evaluacion'] for k, v in referencias(player.session, n).items()}
    equipos = len(player.group.get_players())
    return devolucion.diagnosticar(
        filas, ev, refs, puesto(player), puesto(player, 'sharpe'), equipos,
        terminado=n == num_rondas(player.session), capital=player.session.config['capital_inicial'])


def texto_decision(player):
    # Los porcentajes vienen propuestos de antes: el tablero muestra la decisión solo mientras el equipo espera.
    return f'acciones {player.pct_acciones} %, bonos {player.pct_bonos} %, liquidez {player.pct_liquidez} %'


def actualizar_tablero(player, pagina):
    """Guarda en participant.vars el resumen del equipo para el tablero del docente (nucleo/tablero.py)."""
    etapa, estado = ETAPAS_TABLERO[pagina]
    ev = evaluacion(player)
    ultima = rondas_jugadas(player)[-1] if ev else None
    player.participant.vars['tablero'] = tablero.resumen(
        juego=C.NAME_IN_URL,
        equipo=nombre(player),
        grupo_numero=player.group.id_in_subsession,
        grupo_tipo='grupo',
        grupo_tamano=len(player.group.get_players()),
        posicion=player.id_in_group,
        ronda=player.round_number,
        rondas=num_rondas(player.session),
        etapa=etapa,
        estado=estado,
        puesto=puesto(player) if ev else None,
        indicadores=[
            tablero.indicador('Valor real', ultima.valor_real if ultima else None, 'pesos'),
            tablero.indicador('TEA real', ev['tea_real'] if ev else None, 'pct1', signo=True),
            tablero.indicador('Sharpe', numero(ev['sharpe'], 2) if ev else None, 'texto'),
        ],
        decision=texto_decision(player),
        columnas=COLUMNAS_TABLERO,
        filas=historial(player),
        nota_historial='Valor en pesos de cada trimestre; el valor real está en pesos del inicio del juego.',
        devolucion=devolucion_de(player),
    )


# --- Páginas ------------------------------------------------------------------

class Instrucciones(Page):
    form_model = 'player'
    form_fields = ['nombre_equipo']

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Instrucciones')
        cfg = player.session.config
        n = num_rondas(player.session)
        return dict(
            num_rondas=n,
            anios=texto_anios(n),
            num_equipos=len(player.group.get_players()),
            capital=pesos(cfg['capital_inicial']),
            comision=porcentaje(cfg['comision']),
            inflacion_media=porcentaje(cfg['inflacion_media']),
            inflacion_anual=porcentaje((1 + cfg['inflacion_media']) ** 4 - 1, 0),
            bonos_tasa_real=porcentaje(cfg['bonos_tasa_real']),
            bonos_duracion=numero(cfg['bonos_duracion'], 0),
            tasa_plazo_fijo=porcentaje(cfg['inflacion_media'] + cfg['liquidez_diferencial']),
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        texto = (player.nombre_equipo or '').strip()
        if texto:
            player.participant.vars['nombre_equipo'] = texto


class Decision(Page):
    form_model = 'player'
    form_fields = ['pct_acciones', 'pct_bonos', 'pct_liquidez']

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)

    @staticmethod
    def error_message(player: Player, valores):
        pesos_elegidos = tuple(valores[f'pct_{a}'] / 100 for a in modelo.ACTIVOS)
        return modelo.validar_porcentajes(pesos_elegidos)

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        actualizar_tablero(player, 'Esperando a los demás equipos')

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Decisión')
        cfg = player.session.config
        g = player.group
        r = player.round_number
        ant = anterior(player)
        montos = montos_al_empezar(player)
        valor = sum(montos)
        indice_previo = ant.group.indice if ant else 1.0
        return dict(
            nombre=nombre(player),
            num_rondas=num_rondas(player.session),
            anio=anio_de(r),
            trimestre_del_anio=(r - 1) % 4 + 1,
            ultima=es_ultima_ronda(player),
            titular=titular(g),
            tasa_plazo_fijo=porcentaje(g.rend_liquidez, 2),
            tna_plazo_fijo=porcentaje(g.rend_liquidez * 4, 1),
            bonos_tasa_real=porcentaje(cfg['bonos_tasa_real']),
            comision=porcentaje(cfg['comision']),
            valor=pesos(valor),
            valor_real=pesos(valor / indice_previo),
            hay_anterior=ant is not None,
            composicion=composicion(montos),
            rendimientos=tabla_rendimientos(player, r - 1),
        )


class EsperaResultados(WaitPage):
    title_text = 'Esperando a los demás equipos'
    body_text = 'El trimestre se cierra cuando todos los equipos hayan enviado su decisión.'
    after_all_players_arrive = calcular_resultados

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
        g = player.group
        capital = player.session.config['capital_inicial']
        invertido, _ = modelo.rebalancear(montos_al_empezar(player), pesos_decididos(player),
                                          player.session.config['comision'])
        rend = (g.rend_acciones, g.rend_bonos, g.rend_liquidez)
        finales = (player.monto_acciones, player.monto_bonos, player.monto_liquidez)
        activos = [dict(activo=NOMBRES_ACTIVOS[a], pct=f'{pct} %', invertido=pesos(i), rendimiento=porcentaje(r),
                        negativo=r < 0, final=pesos(f))
                   for a, pct, i, r, f in zip(modelo.ACTIVOS, (player.pct_acciones, player.pct_bonos, player.pct_liquidez),
                                              invertido, rend, finales)]
        return dict(
            nombre=nombre(player),
            num_rondas=num_rondas(player.session),
            crisis=g.crisis,
            inflacion=porcentaje(g.inflacion),
            var_dolar=porcentaje(g.var_dolar),
            acciones_usd=porcentaje(g.acciones_usd),
            activos=activos,
            valor_inicial=pesos(player.valor_inicial),
            comision=pesos(player.comision),
            hubo_comision=player.comision > 0.5,
            valor_final=pesos(player.valor_final),
            rendimiento=porcentaje(player.rendimiento), rendimiento_neg=player.rendimiento < 0,
            rendimiento_real=porcentaje(player.rendimiento_real), rendimiento_real_neg=player.rendimiento_real < 0,
            valor_real=pesos(player.valor_real),
            var_real=porcentaje(player.valor_real / capital - 1), var_real_neg=player.valor_real < capital,
            var_dolares=porcentaje(player.valor_dolares / capital - 1), var_dolares_neg=player.valor_dolares < capital,
            puesto=puesto(player),
            num_equipos=len(g.get_players()),
            fin_de_anio=player.round_number % 4 == 0 or es_ultima_ronda(player),
        )

    @staticmethod
    def js_vars(player: Player):
        return dict(graficos=datos_graficos(player))


class InformeAnual(Page):
    """Al cerrar cada año (y el último tramo si el juego no termina en un año entero)."""

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player) and (player.round_number % 4 == 0 or es_ultima_ronda(player))

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Informe anual')
        n = player.round_number
        ev = evaluacion(player)
        refs = referencias(player.session, n)
        anio = anio_de(n)
        propio = ev['anios'][-1]
        filas_anio = [dict(nombre=f'{nombre(player)} (ustedes)', es_propia=True,
                           rentabilidad=porcentaje(propio['rentabilidad_real']), negativo=propio['rentabilidad_real'] < 0)]
        for nombre_ref, ref in refs.items():
            x = ref['evaluacion']['anios'][-1]['rentabilidad_real']
            filas_anio.append(dict(nombre=nombre_ref, es_propia=False, rentabilidad=porcentaje(x), negativo=x < 0))
        primera = (anio - 1) * 4 + 1
        indice_inicio = player.group.in_round(primera - 1).indice if primera > 1 else 1.0
        return dict(
            nombre=nombre(player),
            anio=anio,
            parcial=texto_parcial(propio['trimestres']),
            inflacion_anio=porcentaje(player.group.indice / indice_inicio - 1),
            anios=[dict(anio=a['anio'], rentabilidad=porcentaje(a['rentabilidad_real']),
                        negativo=a['rentabilidad_real'] < 0) for a in ev['anios']],
            filas_anio=filas_anio,
            ranking=filas_ranking(player, 'valor_real'),
            ultima=es_ultima_ronda(player),
            **indicadores(ev),
        )


class ResultadoFinal(Page):
    @staticmethod
    def is_displayed(player: Player):
        return es_ultima_ronda(player)

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Terminó')
        n = player.round_number
        ev = evaluacion(player)
        refs = referencias(player.session, n)
        filas_ref = [dict(nombre=f'{nombre(player)} (ustedes)', es_propia=True, **indicadores(ev))]
        filas_ref += [dict(nombre=k, es_propia=False, **indicadores(v['evaluacion'])) for k, v in refs.items()]
        return dict(
            nombre=nombre(player),
            num_rondas=n,
            inflacion_acumulada=porcentaje(player.group.indice - 1),
            ranking_tea=filas_ranking(player, 'valor_real'),
            ranking_sharpe=filas_ranking(player, 'sharpe'),
            filas_ref=filas_ref,
            anios=[dict(anio=a['anio'], parcial=texto_parcial(a['trimestres']), rentabilidad=porcentaje(a['rentabilidad_real']),
                        negativo=a['rentabilidad_real'] < 0) for a in ev['anios']],
            devolucion=devolucion_de(player),
            comentario_docente=(player.participant.vars.get('comentario_docente') or '').strip(),
            semilla=player.session.vars.get('semilla'),
            **indicadores(ev),
        )

    @staticmethod
    def js_vars(player: Player):
        return dict(graficos=datos_graficos(player))


page_sequence = [Instrucciones, Decision, EsperaResultados, Resultados, InformeAnual, ResultadoFinal]
