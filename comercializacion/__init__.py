import random

from otree.api import *

from . import mercado


doc = """
Simulador de comercialización (FCEJ - UNLPam).
Varias empresas compiten en un mismo mercado de gaseosas durante varios
trimestres, decidiendo precio, publicidad y producción, y pudiendo comprar
estudios de mercado.
"""

# Parámetros del modelo que se leen de la configuración de la sesión
# (definidos en SESSION_CONFIGS de settings.py).
PARAMETROS_MODELO = mercado.PARAMETROS

# Precios relativos al precio medio anterior que muestra el estudio de sensibilidad.
PRECIOS_SENSIBILIDAD = [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3]

ESTACIONES = {1: 'enero-marzo', 2: 'abril-junio', 3: 'julio-septiembre', 4: 'octubre-diciembre'}


class C(BaseConstants):
    NAME_IN_URL = 'comercializacion'
    PLAYERS_PER_GROUP = 4  # empresas por mercado
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

    # Decisiones
    precio = models.FloatField(label='Precio de venta por unidad ($)')
    publicidad = models.FloatField(label='Inversión en publicidad del trimestre ($)')
    produccion = models.IntegerField(label='Unidades a producir en el trimestre')

    # Estado al empezar el trimestre
    stock_inicial = models.FloatField()

    # Resultados del trimestre
    stock_publicidad = models.FloatField()
    preferencia = models.FloatField()
    demanda = models.FloatField()
    unidades = models.FloatField()
    faltante = models.FloatField()
    participacion = models.FloatField()
    stock_final = models.FloatField()
    ventas = models.FloatField()
    costo_ventas = models.FloatField()
    costo_publicidad = models.FloatField()
    costo_almacenamiento = models.FloatField()
    costo_investigacion = models.FloatField(initial=0)
    costo_fijo = models.FloatField()
    baja_stock = models.FloatField()
    resultado = models.FloatField()
    resultado_acumulado = models.FloatField()


# --- Funciones auxiliares ---------------------------------------------------

def num_rondas(session):
    return min(session.config.get('num_rondas', C.NUM_ROUNDS), C.NUM_ROUNDS)


def ronda_activa(player):
    return player.round_number <= num_rondas(player.session)


def es_ultima_ronda(player_o_group):
    return player_o_group.round_number == num_rondas(player_o_group.session)


def parametros(session):
    return {k: session.config[k] for k in PARAMETROS_MODELO}


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


def porcentaje(x):
    return numero(100 * x, 1) + ' %'


def costos_estudios(session):
    cfg = session.config
    return dict(
        competencia=cfg['costo_estudio_competencia'],
        pronostico=cfg['costo_estudio_pronostico'],
        sensibilidad=cfg['costo_estudio_sensibilidad'],
    )


# Límites dinámicos de los campos (tomados de la configuración de la sesión)

def precio_min(player):
    return player.session.config['precio_min']


def precio_max(player):
    return player.session.config['precio_max']


def publicidad_min(player):
    return 0


def publicidad_max(player):
    return player.session.config['publicidad_max']


def produccion_min(player):
    return 0


def produccion_max(player):
    return int(player.session.config['capacidad'])


# --- Creación de la sesión: estacionalidad y shocks ---------------------------

def creating_session(subsession: Subsession):
    cfg = subsession.session.config
    factores = mercado.factores_estacionales(cfg['estacionalidad'])
    t = mercado.trimestre_del_anio(subsession.round_number, int(cfg['trimestre_inicial']))
    for g in subsession.get_groups():
        # Shock normal truncado en ±2 desvíos, distinto para cada mercado y trimestre.
        z = max(-2.0, min(2.0, random.gauss(0, 1)))
        g.trimestre_anio = t
        g.shock = z * cfg['desvio_shock']
        g.factor_demanda = factores[t - 1] * (1 + g.shock)


# --- Cálculo de resultados ----------------------------------------------------

def estado_inicial(p: Player):
    ant = anterior(p)
    if ant is None:
        return dict(stock_inicial=p.session.config['stock_inicial'], stock_publicidad_anterior=0)
    return dict(stock_inicial=ant.stock_final, stock_publicidad_anterior=ant.stock_publicidad)


def calcular_resultados(group: Group):
    """Se ejecuta cuando todas las empresas del mercado tomaron su decisión."""
    jugadores = group.get_players()
    decisiones = [dict(precio=p.precio, publicidad=p.publicidad, produccion=p.produccion,
                       costo_investigacion=p.costo_investigacion) for p in jugadores]
    estados = [estado_inicial(p) for p in jugadores]
    salida = mercado.simular_ronda(decisiones, estados, parametros(group.session),
                                   factor_demanda=group.factor_demanda,
                                   ultima_ronda=es_ultima_ronda(group))

    group.precio_medio = salida['mercado']['precio_medio']
    group.demanda_total = salida['mercado']['demanda_total']
    group.unidades_vendidas = salida['mercado']['unidades_vendidas']

    for p, e, r in zip(jugadores, estados, salida['empresas']):
        p.stock_inicial = e['stock_inicial']
        for campo, valor in r.items():
            setattr(p, campo, valor)
        ant = anterior(p)
        p.resultado_acumulado = (ant.resultado_acumulado if ant else 0) + p.resultado


# --- Estudios de mercado -------------------------------------------------------

def datos_competencia(player: Player):
    """Decisiones y resultados de los rivales en el trimestre anterior."""
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


def calcular_pronostico(player: Player):
    cfg = player.session.config
    ant = anterior(player)
    p_medio = ant.group.precio_medio if ant else cfg['precio_referencia']
    error = random.uniform(-1, 1) * cfg['error_pronostico']
    return mercado.pronostico_demanda(p_medio, parametros(player.session),
                                      player.group.factor_demanda, error)


def tabla_sensibilidad(player: Player):
    cfg = player.session.config
    ant = anterior(player)
    rivales_ant = ant.group.get_players()
    i = player.id_in_group - 1
    decisiones = [dict(precio=r.precio, publicidad=r.publicidad) for r in rivales_ant]
    estados = [dict(stock_publicidad_anterior=r.stock_publicidad) for r in rivales_ant]
    precios = sorted({min(max(round(ant.group.precio_medio * k, -1), cfg['precio_min']), cfg['precio_max'])
                      for k in PRECIOS_SENSIBILIDAD})
    filas = mercado.sensibilidad_precio(i, precios, decisiones, estados, parametros(player.session))
    c = cfg['costo_variable']
    return [dict(precio=pesos(f['precio'], 2), unidades=numero(f['unidades']),
                 participacion=porcentaje(f['participacion']),
                 margen=pesos(f['unidades'] * (f['precio'] - c)))
            for f in filas]


# --- Páginas ----------------------------------------------------------------

class Instrucciones(Page):
    form_model = 'player'
    form_fields = ['nombre_empresa']

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def vars_for_template(player: Player):
        cfg = player.session.config
        estudios = costos_estudios(player.session)
        return dict(
            num_rondas=num_rondas(player.session),
            num_empresas=C.PLAYERS_PER_GROUP,
            costo_variable=pesos(cfg['costo_variable'], 2),
            costo_fijo=pesos(cfg['costo_fijo']),
            costo_almacenamiento=pesos(cfg['costo_almacenamiento']),
            capacidad=numero(cfg['capacidad']),
            stock_inicial=numero(cfg['stock_inicial']),
            retencion=porcentaje(cfg['retencion_publicidad']).replace(',0', ''),
            precio_min=pesos(cfg['precio_min'], 2),
            precio_max=pesos(cfg['precio_max'], 2),
            publicidad_max=pesos(cfg['publicidad_max']),
            estudio_competencia=pesos(estudios['competencia']),
            estudio_pronostico=pesos(estudios['pronostico']),
            estudio_sensibilidad=pesos(estudios['sensibilidad']),
            estacion_inicial=ESTACIONES[int(cfg['trimestre_inicial'])],
            # Para el desplegable con el modelo matemático
            demanda_base=numero(cfg['demanda_base']),
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
        estudios = costos_estudios(player.session)
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
        estudios = costos_estudios(player.session)
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
    def vars_for_template(player: Player):
        cfg = player.session.config
        ant = anterior(player)
        estado = estado_inicial(player)
        lam = cfg['retencion_publicidad']
        error = cfg['error_pronostico']
        datos = dict(
            nombre=nombre(player),
            num_rondas=num_rondas(player.session),
            estacion=ESTACIONES[player.group.trimestre_anio],
            costo_variable=pesos(cfg['costo_variable'], 2),
            costo_fijo=pesos(cfg['costo_fijo']),
            costo_almacenamiento=pesos(cfg['costo_almacenamiento']),
            precio_min=pesos(cfg['precio_min'], 2),
            precio_max=pesos(cfg['precio_max'], 2),
            publicidad_max=pesos(cfg['publicidad_max']),
            capacidad=numero(cfg['capacidad']),
            stock_inicial=numero(estado['stock_inicial']),
            publicidad_arrastre=pesos(lam * estado['stock_publicidad_anterior']),
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
                pronostico_por_empresa=numero(player.pronostico / C.PLAYERS_PER_GROUP),
                pronostico_precio=pesos(ant.group.precio_medio if ant else cfg['precio_referencia'], 2),
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
            stock_publicidad=pesos(player.stock_publicidad),
            participacion=porcentaje(player.participacion),
            # Resultado
            ventas=pesos(player.ventas),
            costo_ventas=pesos(player.costo_ventas),
            costo_publicidad=pesos(player.costo_publicidad),
            costo_almacenamiento=pesos(player.costo_almacenamiento),
            costo_investigacion=pesos(player.costo_investigacion),
            costo_fijo=pesos(player.costo_fijo),
            baja_stock=pesos(player.baja_stock),
            hubo_baja=player.baja_stock > 0,
            resultado=pesos(player.resultado),
            resultado_negativo=player.resultado < 0,
            resultado_acumulado=pesos(player.resultado_acumulado),
            acumulado_negativo=player.resultado_acumulado < 0,
        )


class ResultadoFinal(Page):
    @staticmethod
    def is_displayed(player: Player):
        return es_ultima_ronda(player)

    @staticmethod
    def vars_for_template(player: Player):
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
        return dict(filas=filas)


page_sequence = [Instrucciones, Investigacion, Decision, EsperaResultados, Resultados, ResultadoFinal]
