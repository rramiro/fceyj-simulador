import random
import time

from otree.api import *

from . import ajustes_otree, devolucion, mercado

# Página propia para "aula completa" (ver ajustes_otree.py).
ajustes_otree.aplicar()


doc = """
Simulador de comercialización (FCEJ - UNLPam).
Varias empresas compiten en un mismo mercado de gaseosas durante varios
trimestres, en un contexto inflacionario, decidiendo precio, publicidad y
producción, y pudiendo comprar estudios de mercado.
"""

# Parámetros del modelo que se leen de la configuración de la sesión
# (definidos en SESSION_CONFIGS de settings.py).
PARAMETROS_MODELO = mercado.PARAMETROS

# Precios relativos al precio medio de referencia que muestra el estudio de sensibilidad.
PRECIOS_SENSIBILIDAD = [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3]

ESTACIONES = {1: 'enero-marzo', 2: 'abril-junio', 3: 'julio-septiembre', 4: 'octubre-diciembre'}

# Colores de los gráficos (identidad de la FCEyJ). El índigo identifica a la empresa propia.
COLOR_PROPIO = '#2F2E70'
COLOR_MERCADO = '#3B9AD7'
COLORES_RIVALES = ['#3B9AD7', '#8FB3DE', '#9AA5B1', '#5FB3B3', '#C9A227', '#B07AA1', '#7F8C8D']


class C(BaseConstants):
    NAME_IN_URL = 'comercializacion'
    # Los mercados se arman en creating_session con el tamaño objetivo de la configuración
    # ('empresas_por_mercado'), así la sesión admite cualquier cantidad de equipos.
    PLAYERS_PER_GROUP = None
    # Máximo de rondas (trimestres). La cantidad efectiva se define con
    # 'num_rondas' en la configuración de la sesión (no puede superar este valor).
    NUM_ROUNDS = 6
    NOMBRES_EMPRESAS = ['Empresa A', 'Empresa B', 'Empresa C', 'Empresa D',
                        'Empresa E', 'Empresa F', 'Empresa G', 'Empresa H']


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    trimestre_anio = models.IntegerField()   # 1 a 4
    shock = models.FloatField()              # variación aleatoria de la demanda (sorteada al crear la sesión)
    factor_demanda = models.FloatField()     # estacionalidad * (1 + shock)
    inflacion = models.FloatField()          # inflación del trimestre (igual para toda la sesión)
    indice = models.FloatField()             # índice de precios (1 = primer trimestre)
    tasa_financiera = models.FloatField()    # costo financiero del stock en el trimestre
    precio_medio = models.FloatField()
    demanda_total = models.FloatField()
    unidades_vendidas = models.FloatField()


class Player(BasePlayer):
    # Identificación (se completa en la ronda 1 y se copia a las demás)
    nombre_empresa = models.StringField(
        label='Nombre de su empresa', max_length=30, blank=True
    )

    # Investigación de mercado (se compra antes de decidir)
    compra_competencia = models.BooleanField(
        label='Datos de la competencia', widget=widgets.CheckboxInput, blank=True, initial=False)
    compra_pronostico = models.BooleanField(
        label='Pronóstico de demanda', widget=widgets.CheckboxInput, blank=True, initial=False)
    compra_sensibilidad = models.BooleanField(
        label='Sensibilidad al precio', widget=widgets.CheckboxInput, blank=True, initial=False)
    pronostico = models.FloatField()  # demanda total pronosticada (si compró el estudio)

    # Decisiones (en pesos del trimestre)
    precio = models.FloatField(label='Precio de venta por unidad ($)')
    publicidad = models.FloatField(label='Inversión en publicidad del trimestre ($)')
    produccion = models.IntegerField(label='Unidades a producir en el trimestre')

    # Estado al empezar el trimestre
    stock_inicial = models.FloatField()
    valor_stock_inicial = models.FloatField()

    # Resultados del trimestre (pesos nominales del trimestre)
    stock_publicidad = models.FloatField()
    preferencia = models.FloatField()
    demanda = models.FloatField()
    unidades = models.FloatField()
    faltante = models.FloatField()
    participacion = models.FloatField()
    stock_final = models.FloatField()
    costo_unitario = models.FloatField()
    valor_stock_final = models.FloatField()
    ventas = models.FloatField()
    costo_ventas = models.FloatField()
    costo_publicidad = models.FloatField()
    costo_almacenamiento = models.FloatField()
    costo_financiero = models.FloatField()
    costo_investigacion = models.FloatField(initial=0)
    costo_fijo = models.FloatField()
    baja_stock = models.FloatField()
    resultado = models.FloatField()
    # Acumulado en moneda constante: pesos de este trimestre
    resultado_acumulado = models.FloatField()


# --- Funciones auxiliares ---------------------------------------------------

def num_rondas(session):
    return min(session.config.get('num_rondas', C.NUM_ROUNDS), C.NUM_ROUNDS)


def ronda_activa(player):
    return player.round_number <= num_rondas(player.session)


def es_ultima_ronda(player_o_group):
    return player_o_group.round_number == num_rondas(player_o_group.session)


def empresas_en_mercado(player_o_group):
    g = player_o_group if isinstance(player_o_group, Group) else player_o_group.group
    return len(g.get_players())


def parametros(group):
    """Parámetros del modelo para un mercado: la demanda base depende de cuántas empresas tiene."""
    cfg = group.session.config
    datos = {k: cfg[k] for k in PARAMETROS_MODELO if k != 'demanda_base'}
    if 'demanda_por_empresa' in cfg:
        datos['demanda_base'] = mercado.demanda_del_mercado(cfg['demanda_por_empresa'], empresas_en_mercado(group))
    else:
        # Sesiones creadas antes de esta versión: demanda del mercado fija, como entonces.
        datos['demanda_base'] = cfg['demanda_base']
    return datos


def nombre(player):
    return player.participant.vars.get('nombre_empresa') or \
        C.NOMBRES_EMPRESAS[player.id_in_group - 1]


def anterior(player):
    return player.in_round(player.round_number - 1) if player.round_number > 1 else None


def pesos(x, decimales=0):
    """Formatea un número como pesos al estilo argentino: $ 1.234.567,89"""
    s = f'{abs(x):,.{decimales}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('-$ ' if x < 0 else '$ ') + s


def numero(x, decimales=0):
    return f'{x:,.{decimales}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def porcentaje(x, decimales=1):
    return numero(100 * x, decimales) + ' %'


def indice(player_o_group):
    g = player_o_group if isinstance(player_o_group, Group) else player_o_group.group
    return g.indice


def costos_estudios(player):
    """Costo de cada estudio en pesos del trimestre."""
    cfg = player.session.config
    i = indice(player)
    return dict(
        competencia=cfg['costo_estudio_competencia'] * i,
        pronostico=cfg['costo_estudio_pronostico'] * i,
        sensibilidad=cfg['costo_estudio_sensibilidad'] * i,
    )


# Límites dinámicos de los campos (en pesos del trimestre)

def precio_min(player):
    return round(player.session.config['precio_min'] * indice(player), 2)


def precio_max(player):
    return round(player.session.config['precio_max'] * indice(player), 2)


def publicidad_min(player):
    return 0


def publicidad_max(player):
    return round(player.session.config['publicidad_max'] * indice(player))


def produccion_min(player):
    return 0


def produccion_max(player):
    return int(player.session.config['capacidad'])


# --- Creación de la sesión: estacionalidad, shocks e inflación ---------------

def truncada(rnd=random):
    """Normal estándar truncada en ±2 desvíos."""
    return max(-2.0, min(2.0, rnd.gauss(0, 1)))


def creating_session(subsession: Subsession):
    session = subsession.session
    cfg = session.config

    # Mercados: en el primer trimestre se reparten las empresas en mercados lo más parejos
    # posible (sin superar el tamaño objetivo); después se mantienen los mismos.
    if subsession.round_number == 1:
        jugadores = sorted(subsession.get_players(), key=lambda p: p.id_in_subsession)
        tamanos = mercado.repartir_mercados(len(jugadores), cfg.get('empresas_por_mercado', 4))
        matriz, inicio = [], 0
        for tam in tamanos:
            matriz.append(jugadores[inicio:inicio + tam])
            inicio += tam
        subsession.set_group_matrix(matriz)
    else:
        subsession.group_like_round(1)

    # La senda de inflación es una sola para toda la sesión (es macroeconómica).
    if subsession.round_number == 1:
        inflaciones, indices = [0.0], [1.0]
        for _ in range(C.NUM_ROUNDS - 1):
            pi = max(0.0, cfg['inflacion_media'] + truncada() * cfg['inflacion_desvio'])
            inflaciones.append(pi)
            indices.append(mercado.siguiente_indice(indices[-1], pi))
        session.vars['inflacion'] = inflaciones
        session.vars['indice'] = indices

    r = subsession.round_number - 1
    pi = session.vars['inflacion'][r]
    # En el primer trimestre no hay inflación observada: se usa la media esperada.
    tasa = (pi if subsession.round_number > 1 else cfg['inflacion_media']) + cfg['tasa_real']

    factores = mercado.factores_estacionales(cfg['estacionalidad'])
    t = mercado.trimestre_del_anio(subsession.round_number, int(cfg['trimestre_inicial']))
    for g in subsession.get_groups():
        g.trimestre_anio = t
        g.shock = truncada() * cfg['desvio_shock']   # distinto para cada mercado
        g.factor_demanda = factores[t - 1] * (1 + g.shock)
        g.inflacion = pi
        g.indice = session.vars['indice'][r]
        g.tasa_financiera = tasa


# --- Cálculo de resultados ----------------------------------------------------

def estado_inicial(p: Player):
    ant = anterior(p)
    if ant is None:
        cfg = p.session.config
        return dict(stock_inicial=cfg['stock_inicial'],
                    valor_stock_inicial=cfg['stock_inicial'] * cfg['costo_variable'],
                    stock_publicidad_anterior=0)
    return dict(stock_inicial=ant.stock_final, valor_stock_inicial=ant.valor_stock_final,
                stock_publicidad_anterior=ant.stock_publicidad)


def calcular_resultados(group: Group):
    """Se ejecuta cuando todas las empresas del mercado tomaron su decisión."""
    jugadores = group.get_players()
    decisiones = [dict(precio=p.precio, publicidad=p.publicidad, produccion=p.produccion,
                       costo_investigacion=p.costo_investigacion) for p in jugadores]
    estados = [estado_inicial(p) for p in jugadores]
    salida = mercado.simular_ronda(decisiones, estados, parametros(group),
                                   factor_demanda=group.factor_demanda,
                                   ultima_ronda=es_ultima_ronda(group),
                                   indice=group.indice,
                                   tasa_financiera=group.tasa_financiera)

    group.precio_medio = salida['mercado']['precio_medio']
    group.demanda_total = salida['mercado']['demanda_total']
    group.unidades_vendidas = salida['mercado']['unidades_vendidas']

    for p, e, r in zip(jugadores, estados, salida['empresas']):
        p.stock_inicial = e['stock_inicial']
        p.valor_stock_inicial = e['valor_stock_inicial']
        for campo, valor in r.items():
            setattr(p, campo, valor)
        ant = anterior(p)
        p.resultado_acumulado = mercado.acumular_constante(
            ant.resultado_acumulado if ant else 0,
            ant.group.indice if ant else 1.0,
            p.resultado, group.indice)

    # Recién con todos los acumulados se puede calcular el puesto de cada uno.
    for p in jugadores:
        actualizar_tablero(p, 'Resultados listos')


# --- Estudios de mercado -------------------------------------------------------

def datos_competencia(player: Player):
    """Decisiones y resultados de los rivales en el trimestre anterior (pesos de ese trimestre)."""
    ant = anterior(player)
    filas = []
    for r in ant.get_others_in_group():
        filas.append(dict(
            nombre=nombre(r),
            precio=pesos(r.precio, 2),
            publicidad=pesos(r.publicidad),
            produccion=numero(r.produccion),
            unidades=numero(r.unidades),
            stock_final=numero(r.stock_final),
        ))
    return filas


def precio_medio_esperado(player: Player):
    """Precio medio del trimestre anterior actualizado por la inflación (o p_ref en el primero)."""
    cfg = player.session.config
    ant = anterior(player)
    if ant is None:
        return cfg['precio_referencia']
    return ant.group.precio_medio * (1 + player.group.inflacion)


def calcular_pronostico(player: Player):
    cfg = player.session.config
    error = random.uniform(-1, 1) * cfg['error_pronostico']
    return mercado.pronostico_demanda(precio_medio_esperado(player), parametros(player.group),
                                      player.group.factor_demanda, error, player.group.indice)


def tabla_sensibilidad(player: Player):
    """Los rivales repiten su decisión anterior actualizada por la inflación."""
    cfg = player.session.config
    ant = anterior(player)
    ajuste = 1 + player.group.inflacion
    i_actual = player.group.indice
    rivales_ant = ant.group.get_players()
    i = player.id_in_group - 1
    decisiones = [dict(precio=r.precio * ajuste, publicidad=r.publicidad * ajuste) for r in rivales_ant]
    estados = [dict(stock_publicidad_anterior=r.stock_publicidad) for r in rivales_ant]
    base = precio_medio_esperado(player)
    pmin, pmax = cfg['precio_min'] * i_actual, cfg['precio_max'] * i_actual
    precios = sorted({min(max(round(base * k, -1), pmin), pmax) for k in PRECIOS_SENSIBILIDAD})
    filas = mercado.sensibilidad_precio(i, precios, decisiones, estados,
                                        parametros(player.group), i_actual)
    c = cfg['costo_variable'] * i_actual
    return [dict(precio=pesos(f['precio'], 2), unidades=numero(f['unidades']),
                 participacion=porcentaje(f['participacion']),
                 margen=pesos(f['unidades'] * (f['precio'] - c)))
            for f in filas]


# --- Estado de resultados y gráficos -------------------------------------------

FILAS_ESTADO = [
    # (clave, rótulo, signo, tipo)  tipo: '' normal, 'subtotal', 'resultado'
    ('ventas', 'Ventas', 1, ''),
    ('costo_ventas', '− Costo de ventas', -1, ''),
    ('margen_bruto', 'Margen bruto', 1, 'subtotal'),
    ('costo_publicidad', '− Publicidad', -1, ''),
    ('costo_investigacion', '− Estudios de mercado', -1, ''),
    ('costo_almacenamiento', '− Almacenamiento', -1, ''),
    ('costo_financiero', '− Costo financiero del stock', -1, ''),
    ('costo_fijo', '− Costo fijo', -1, ''),
    ('baja_stock', '− Baja del stock sobrante', -1, ''),
    ('resultado', 'Resultado', 1, 'resultado'),
]


def estado_resultados(player: Player):
    """
    Estado de resultados de los trimestres jugados: una columna nominal por
    trimestre y una columna total reexpresada en pesos del último trimestre.
    """
    rondas = [p for p in player.in_rounds(1, player.round_number)]
    i_final = player.group.indice

    def valor(p, clave):
        if clave == 'margen_bruto':
            return p.ventas - p.costo_ventas
        return getattr(p, clave)

    filas = []
    for clave, rotulo, signo, tipo in FILAS_ESTADO:
        nominales = [signo * valor(p, clave) for p in rondas]
        if clave == 'baja_stock' and not any(nominales):
            continue
        total = sum(mercado.reexpresar(v, p.group.indice, i_final) for v, p in zip(nominales, rondas))
        filas.append(dict(
            rotulo=rotulo, tipo=tipo,
            valores=[dict(texto=pesos(v), negativo=v < 0) for v in nominales],
            total=pesos(total), total_negativo=total < 0,
        ))
    return dict(
        columnas=[f'T{p.round_number}' for p in rondas],
        filas=filas,
        inflacion=[porcentaje(p.group.inflacion) if p.round_number > 1 else '—' for p in rondas],
        indices=[numero(p.group.indice, 3) for p in rondas],
        trimestre_final=f'T{player.round_number}',
    )


def datos_graficos(player: Player):
    """Series para los gráficos de evolución (respetan la información pública)."""
    rondas = player.in_rounds(1, player.round_number)
    i_final = player.group.indice
    etiquetas = [f'T{p.round_number}' for p in rondas]

    # Precio: propio y medio del mercado; precios de rivales solo donde se compró el estudio.
    precio = [
        dict(nombre='Su precio', valores=[p.precio for p in rondas], color=COLOR_PROPIO, ancho=3),
        dict(nombre='Precio medio', valores=[p.group.precio_medio for p in rondas],
             color=COLOR_MERCADO, punteada=True),
    ]
    rivales = [r for r in player.group.get_players() if r.id_in_group != player.id_in_group]
    for k, rival in enumerate(rivales):
        valores = []
        for p in rondas:
            # El estudio del trimestre t+1 revela el precio del trimestre t.
            siguiente = p.round_number + 1
            visto = siguiente <= player.round_number and player.in_round(siguiente).compra_competencia
            valores.append(rival.in_round(p.round_number).precio if visto else None)
        if any(v is not None for v in valores):
            precio.append(dict(nombre=f'{nombre(rival)} (estudio)', valores=valores,
                               color=COLORES_RIVALES[k % len(COLORES_RIVALES)], solo_puntos=True))

    # Participación en ventas: pública para todas las empresas.
    participacion = []
    for k, emp in enumerate(player.group.get_players()):
        propia = emp.id_in_group == player.id_in_group
        participacion.append(dict(
            nombre=nombre(emp) + (' (ustedes)' if propia else ''),
            valores=[emp.in_round(p.round_number).participacion for p in rondas],
            color=COLOR_PROPIO if propia else COLORES_RIVALES[k % len(COLORES_RIVALES)],
            ancho=3 if propia else 2,
        ))
    participacion.sort(key=lambda s: s['color'] != COLOR_PROPIO)

    # Resultado propio en moneda constante (pesos del último trimestre).
    resultado = [mercado.reexpresar(p.resultado, p.group.indice, i_final) for p in rondas]
    acumulado = [mercado.reexpresar(p.resultado_acumulado, p.group.indice, i_final) for p in rondas]

    return dict(
        etiquetas=etiquetas,
        precio=precio,
        participacion=participacion,
        resultado=resultado,
        acumulado=acumulado,
        color_acumulado=COLOR_PROPIO,
        trimestre_final=f'T{player.round_number}',
    )


# --- Tablero del docente y devolución -----------------------------------------
#
# El tablero del docente (_static/docente/) lee estos datos con la API REST de
# oTree, que solo expone participant.vars. Por eso cada página guarda acá un
# resumen del estado del equipo (todo en tipos JSON).

def rondas_jugadas(player: Player):
    """Rondas de este jugador que ya tienen resultados calculados."""
    return [p for p in player.in_rounds(1, player.round_number)
            if p.field_maybe_none('resultado') is not None]


def historial(player: Player):
    """Datos por trimestre para la devolución y el tablero."""
    filas = []
    for p in rondas_jugadas(player):
        otros = p.get_others_in_group()
        filas.append(dict(
            trimestre=p.round_number,
            precio=p.precio,
            precio_medio=p.group.precio_medio,
            publicidad=p.publicidad,
            publicidad_rivales=sum(o.publicidad for o in otros) / len(otros) if otros else 0,
            produccion=p.produccion,
            demanda=p.demanda,
            unidades=p.unidades,
            faltante=p.faltante,
            stock_final=p.stock_final,
            participacion=p.participacion,
            ventas=p.ventas,
            costo_ventas=p.costo_ventas,
            costo_almacenamiento=p.costo_almacenamiento,
            costo_financiero=p.costo_financiero,
            costo_investigacion=p.costo_investigacion,
            baja_stock=p.baja_stock,
            resultado=p.resultado,
            resultado_acumulado=p.resultado_acumulado,
            inflacion=p.group.inflacion,
            indice=p.group.indice,
            estudios=int(bool(p.compra_competencia)) + int(bool(p.compra_pronostico))
            + int(bool(p.compra_sensibilidad)),
        ))
    return filas


def puesto_en_mercado(player: Player):
    """Posición por resultado acumulado en la última ronda con resultados."""
    jugadas = rondas_jugadas(player)
    if not jugadas:
        return None
    ultima = jugadas[-1]
    acumulados = sorted((p.resultado_acumulado for p in ultima.group.get_players()), reverse=True)
    return acumulados.index(ultima.resultado_acumulado) + 1


def devolucion_de(player: Player):
    filas = historial(player)
    puesto = puesto_en_mercado(player)
    if puesto is None:
        return []
    terminado = filas[-1]['trimestre'] == num_rondas(player.session)
    return devolucion.diagnosticar(filas, puesto, empresas_en_mercado(player), terminado)


def actualizar_tablero(player: Player, pagina: str):
    """Guarda en participant.vars el estado del equipo para el tablero del docente."""
    decidio = player.field_maybe_none('precio') is not None
    player.participant.vars['tablero'] = dict(
        empresa=nombre(player),
        mercado=player.group.id_in_subsession,
        empresas_por_mercado=empresas_en_mercado(player),
        id_en_mercado=player.id_in_group,
        trimestre=player.round_number,
        num_trimestres=num_rondas(player.session),
        pagina=pagina,
        decision=dict(precio=player.precio, publicidad=player.publicidad, produccion=player.produccion,
                      estudios=[e for e, v in (('competencia', player.compra_competencia),
                                               ('pronóstico', player.compra_pronostico),
                                               ('sensibilidad', player.compra_sensibilidad)) if v])
        if decidio else None,
        inflacion=player.group.inflacion,
        indice=player.group.indice,
        puesto=puesto_en_mercado(player),
        historial=historial(player),
        devolucion=devolucion_de(player),
        actualizado=time.time(),
    )


# --- Páginas ----------------------------------------------------------------

class Instrucciones(Page):
    form_model = 'player'
    form_fields = ['nombre_empresa']

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Instrucciones')
        cfg = player.session.config
        estudios = costos_estudios(player)
        return dict(
            num_rondas=num_rondas(player.session),
            num_empresas=empresas_en_mercado(player),
            costo_variable=pesos(cfg['costo_variable'], 2),
            costo_fijo=pesos(cfg['costo_fijo']),
            costo_almacenamiento=pesos(cfg['costo_almacenamiento']),
            capacidad=numero(cfg['capacidad']),
            stock_inicial=numero(cfg['stock_inicial']),
            retencion=porcentaje(cfg['retencion_publicidad'], 0),
            inflacion_media=porcentaje(cfg['inflacion_media'], 0),
            inflacion_anual=porcentaje((1 + cfg['inflacion_media']) ** 4 - 1, 0),
            tasa_real=porcentaje(cfg['tasa_real'], 0),
            precio_min=pesos(cfg['precio_min'], 2),
            precio_max=pesos(cfg['precio_max'], 2),
            publicidad_max=pesos(cfg['publicidad_max']),
            estudio_competencia=pesos(estudios['competencia']),
            estudio_pronostico=pesos(estudios['pronostico']),
            estudio_sensibilidad=pesos(estudios['sensibilidad']),
            estacion_inicial=ESTACIONES[int(cfg['trimestre_inicial'])],
            # Para el desplegable con el modelo matemático
            demanda_base=numero(parametros(player.group)['demanda_base']),
            precio_referencia=numero(cfg['precio_referencia']),
            elasticidad=numero(cfg['elasticidad'], 2),
            beta_precio=numero(cfg['beta_precio'], 2),
            beta_publicidad=numero(cfg['beta_publicidad'], 2),
            escala_publicidad=numero(cfg['escala_publicidad']),
            lambda_pub=numero(cfg['retencion_publicidad'], 2),
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        texto = (player.nombre_empresa or '').strip()
        if texto:
            player.participant.vars['nombre_empresa'] = texto


class Investigacion(Page):
    form_model = 'player'

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)

    @staticmethod
    def get_form_fields(player: Player):
        # Los estudios sobre el trimestre anterior solo existen desde el trimestre 2.
        if player.round_number == 1:
            return ['compra_pronostico']
        return ['compra_competencia', 'compra_pronostico', 'compra_sensibilidad']

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Investigación de mercado')
        estudios = costos_estudios(player)
        return dict(
            nombre=nombre(player),
            num_rondas=num_rondas(player.session),
            primera=player.round_number == 1,
            estudio_competencia=pesos(estudios['competencia']),
            estudio_pronostico=pesos(estudios['pronostico']),
            estudio_sensibilidad=pesos(estudios['sensibilidad']),
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        estudios = costos_estudios(player)
        player.costo_investigacion = (
            (estudios['competencia'] if player.compra_competencia else 0)
            + (estudios['pronostico'] if player.compra_pronostico else 0)
            + (estudios['sensibilidad'] if player.compra_sensibilidad else 0)
        )
        if player.compra_pronostico:
            player.pronostico = calcular_pronostico(player)


class Decision(Page):
    form_model = 'player'
    form_fields = ['precio', 'publicidad', 'produccion']

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        actualizar_tablero(player, 'Esperando a las demás empresas')

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Decisión')
        cfg = player.session.config
        g = player.group
        ant = anterior(player)
        estado = estado_inicial(player)
        lam = cfg['retencion_publicidad']
        error = cfg['error_pronostico']
        i_t = g.indice
        datos = dict(
            nombre=nombre(player),
            num_rondas=num_rondas(player.session),
            estacion=ESTACIONES[g.trimestre_anio],
            inflacion=porcentaje(g.inflacion),
            hay_inflacion=player.round_number > 1,
            inflacion_acumulada=porcentaje(i_t - 1),
            tasa_financiera=porcentaje(g.tasa_financiera),
            costo_variable=pesos(cfg['costo_variable'] * i_t, 2),
            costo_fijo=pesos(cfg['costo_fijo'] * i_t),
            costo_almacenamiento=pesos(cfg['costo_almacenamiento'] * i_t, 2),
            precio_min=pesos(precio_min(player), 2),
            precio_max=pesos(precio_max(player), 2),
            publicidad_max=pesos(publicidad_max(player)),
            capacidad=numero(cfg['capacidad']),
            stock_inicial=numero(estado['stock_inicial']),
            valor_stock=pesos(estado['valor_stock_inicial']),
            hay_stock=estado['stock_inicial'] > 0.5,
            costo_unitario_stock=pesos(estado['valor_stock_inicial'] / estado['stock_inicial'], 2)
            if estado['stock_inicial'] > 0.5 else None,
            publicidad_arrastre=pesos(lam * estado['stock_publicidad_anterior'] * i_t),
            ultima=es_ultima_ronda(player),
            anterior=ant,
            costo_investigacion=pesos(player.costo_investigacion),
            # Estudios comprados
            ver_competencia=bool(player.compra_competencia),
            ver_pronostico=bool(player.compra_pronostico),
            ver_sensibilidad=bool(player.compra_sensibilidad),
        )
        if ant:
            datos.update(
                anterior_precio=pesos(ant.precio, 2),
                anterior_publicidad=pesos(ant.publicidad),
                anterior_resultado=pesos(ant.resultado),
                anterior_negativo=ant.resultado < 0,
                anterior_participacion=porcentaje(ant.participacion),
                anterior_precio_medio=pesos(ant.group.precio_medio, 2),
                anterior_unidades=numero(ant.unidades),
                anterior_faltante=numero(ant.faltante) if ant.faltante > 0.5 else None,
            )
        if player.compra_competencia:
            datos['competencia'] = datos_competencia(player)
        if player.compra_pronostico:
            datos.update(
                pronostico_min=numero(player.pronostico * (1 - error)),
                pronostico_max=numero(player.pronostico * (1 + error)),
                pronostico_por_empresa=numero(player.pronostico / empresas_en_mercado(player)),
                pronostico_precio=pesos(precio_medio_esperado(player), 2),
            )
        if player.compra_sensibilidad:
            datos['sensibilidad'] = tabla_sensibilidad(player)
        return datos


class EsperaResultados(WaitPage):
    title_text = 'Esperando a las demás empresas'
    body_text = 'Los resultados se calculan cuando todas las empresas del mercado hayan enviado su decisión.'
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
        # Información pública: participación en ventas de cada empresa.
        mercado_filas = [
            dict(nombre=nombre(p), es_propia=(p.id == player.id),
                 participacion=porcentaje(p.participacion))
            for p in sorted(g.get_players(), key=lambda p: p.participacion, reverse=True)
        ]
        return dict(
            nombre=nombre(player),
            num_rondas=num_rondas(player.session),
            estacion=ESTACIONES[g.trimestre_anio],
            inflacion=porcentaje(g.inflacion),
            hay_inflacion=player.round_number > 1,
            precio_medio=pesos(g.precio_medio, 2),
            demanda_total=numero(g.demanda_total),
            unidades_vendidas=numero(g.unidades_vendidas),
            mercado_filas=mercado_filas,
            ultima=es_ultima_ronda(player),
            # Unidades
            stock_inicial=numero(player.stock_inicial),
            produccion=numero(player.produccion),
            demanda=numero(player.demanda),
            unidades=numero(player.unidades),
            faltante=numero(player.faltante),
            hubo_faltante=player.faltante > 0.5,
            stock_final=numero(player.stock_final),
            valor_stock_final=pesos(player.valor_stock_final),
            costo_unitario=pesos(player.costo_unitario, 2),
            stock_publicidad=pesos(player.stock_publicidad * g.indice),
            participacion=porcentaje(player.participacion),
            # Resultado
            ventas=pesos(player.ventas),
            costo_ventas=pesos(player.costo_ventas),
            costo_publicidad=pesos(player.costo_publicidad),
            costo_almacenamiento=pesos(player.costo_almacenamiento),
            costo_financiero=pesos(player.costo_financiero),
            tasa_financiera=porcentaje(g.tasa_financiera),
            costo_investigacion=pesos(player.costo_investigacion),
            costo_fijo=pesos(player.costo_fijo),
            baja_stock=pesos(player.baja_stock),
            hubo_baja=player.baja_stock > 0,
            resultado=pesos(player.resultado),
            resultado_negativo=player.resultado < 0,
            resultado_acumulado=pesos(player.resultado_acumulado),
            acumulado_negativo=player.resultado_acumulado < 0,
            mostrar_evolucion=player.round_number > 1,
            estado=estado_resultados(player),
        )

    @staticmethod
    def js_vars(player: Player):
        return dict(graficos=datos_graficos(player))


class ResultadoFinal(Page):
    @staticmethod
    def is_displayed(player: Player):
        return es_ultima_ronda(player)

    @staticmethod
    def vars_for_template(player: Player):
        actualizar_tablero(player, 'Terminó')
        ranking = sorted(player.group.get_players(),
                         key=lambda p: p.resultado_acumulado, reverse=True)
        filas = [
            dict(
                puesto=i + 1,
                nombre=nombre(p),
                es_propia=(p.id == player.id),
                resultado_acumulado=pesos(p.resultado_acumulado),
                acumulado_negativo=p.resultado_acumulado < 0,
            )
            for i, p in enumerate(ranking)
        ]
        return dict(
            filas=filas,
            nombre=nombre(player),
            trimestre_final=f'T{player.round_number}',
            inflacion_acumulada=porcentaje(player.group.indice - 1),
            estado=estado_resultados(player),
            devolucion=devolucion_de(player),
            # Lo escribe el docente desde su tablero (se guarda en participant.vars por la API).
            comentario_docente=(player.participant.vars.get('comentario_docente') or '').strip(),
        )

    @staticmethod
    def js_vars(player: Player):
        return dict(graficos=datos_graficos(player))


page_sequence = [Instrucciones, Investigacion, Decision, EsperaResultados, Resultados, ResultadoFinal]
