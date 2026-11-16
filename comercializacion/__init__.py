from otree.api import *

from . import mercado


doc = """
Simulador de comercialización (FCEJ - UNLPam).
Varias empresas compiten en un mismo mercado de gaseosas durante varios
trimestres, decidiendo precio e inversión en publicidad.
"""

# Parámetros del modelo que se leen de la configuración de la sesión
# (definidos en SESSION_CONFIGS de settings.py).
PARAMETROS_MODELO = mercado.PARAMETROS


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
    precio_medio = models.FloatField()
    demanda_total = models.FloatField()


class Player(BasePlayer):
    # Identificación (se completa en la ronda 1 y se copia a las demás)
    nombre_empresa = models.StringField(
        label='Nombre de su empresa', max_length=30, blank=True
    )

    # Decisiones
    precio = models.FloatField(label='Precio de venta por unidad ($)')
    publicidad = models.FloatField(label='Inversión en publicidad del trimestre ($)')

    # Resultados de la ronda
    participacion = models.FloatField()
    unidades = models.FloatField()
    ventas = models.FloatField()
    costo_variable = models.FloatField()
    costo_publicidad = models.FloatField()
    costo_fijo = models.FloatField()
    resultado = models.FloatField()
    resultado_acumulado = models.FloatField()


# --- Funciones auxiliares ---------------------------------------------------

def num_rondas(session):
    return min(session.config.get('num_rondas', C.NUM_ROUNDS), C.NUM_ROUNDS)


def ronda_activa(player):
    return player.round_number <= num_rondas(player.session)


def parametros(session):
    return {k: session.config[k] for k in PARAMETROS_MODELO}


def nombre(player):
    return player.participant.vars.get('nombre_empresa') or \
        C.NOMBRES_EMPRESAS[player.id_in_group - 1]


def pesos(x, decimales=0):
    """Formatea un número como pesos al estilo argentino: $ 1.234.567,89"""
    s = f'{abs(x):,.{decimales}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('-$ ' if x < 0 else '$ ') + s


def numero(x, decimales=0):
    return f'{x:,.{decimales}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def porcentaje(x):
    return numero(100 * x, 1) + ' %'


# Límites dinámicos de los campos (tomados de la configuración de la sesión)

def precio_min(player):
    return player.session.config['precio_min']


def precio_max(player):
    return player.session.config['precio_max']


def publicidad_min(player):
    return 0


def publicidad_max(player):
    return player.session.config['publicidad_max']


def calcular_resultados(group: Group):
    """Se ejecuta cuando todas las empresas del mercado tomaron su decisión."""
    jugadores = group.get_players()
    decisiones = [dict(precio=p.precio, publicidad=p.publicidad) for p in jugadores]
    salida = mercado.simular_ronda(decisiones, parametros(group.session))

    group.precio_medio = salida['mercado']['precio_medio']
    group.demanda_total = salida['mercado']['demanda_total']

    for p, r in zip(jugadores, salida['empresas']):
        for campo, valor in r.items():
            setattr(p, campo, valor)
        anterior = p.in_round(p.round_number - 1).resultado_acumulado \
            if p.round_number > 1 else 0
        p.resultado_acumulado = anterior + p.resultado


def filas_resultados(group: Group, jugador_actual):
    """Filas de la tabla comparativa de la ronda."""
    filas = []
    for p in group.get_players():
        filas.append(dict(
            nombre=nombre(p),
            es_propia=(p.id == jugador_actual.id),
            precio=pesos(p.precio, 2),
            publicidad=pesos(p.publicidad),
            participacion=porcentaje(p.participacion),
            unidades=numero(p.unidades),
            ventas=pesos(p.ventas),
            resultado=pesos(p.resultado),
            resultado_negativo=p.resultado < 0,
            resultado_acumulado=pesos(p.resultado_acumulado),
            acumulado_negativo=p.resultado_acumulado < 0,
        ))
    return filas


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
        return dict(
            num_rondas=num_rondas(player.session),
            num_empresas=C.PLAYERS_PER_GROUP,
            costo_variable=pesos(cfg['costo_variable'], 2),
            costo_fijo=pesos(cfg['costo_fijo']),
            precio_min=pesos(cfg['precio_min'], 2),
            precio_max=pesos(cfg['precio_max'], 2),
            publicidad_max=pesos(cfg['publicidad_max']),
            # Para el desplegable con el modelo matemático
            demanda_base=numero(cfg['demanda_base']),
            precio_referencia=numero(cfg['precio_referencia']),
            elasticidad=numero(cfg['elasticidad'], 2),
            beta_precio=numero(cfg['beta_precio'], 2),
            beta_publicidad=numero(cfg['beta_publicidad'], 2),
            escala_publicidad=numero(cfg['escala_publicidad']),
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        texto = (player.nombre_empresa or '').strip()
        if texto:
            player.participant.vars['nombre_empresa'] = texto


class Decision(Page):
    form_model = 'player'
    form_fields = ['precio', 'publicidad']

    @staticmethod
    def is_displayed(player: Player):
        return ronda_activa(player)

    @staticmethod
    def vars_for_template(player: Player):
        cfg = player.session.config
        anterior = player.in_round(player.round_number - 1) \
            if player.round_number > 1 else None
        return dict(
            nombre=nombre(player),
            num_rondas=num_rondas(player.session),
            costo_variable=pesos(cfg['costo_variable'], 2),
            costo_fijo=pesos(cfg['costo_fijo']),
            anterior=anterior,
            anterior_precio=pesos(anterior.precio, 2) if anterior else None,
            anterior_publicidad=pesos(anterior.publicidad) if anterior else None,
            anterior_resultado=pesos(anterior.resultado) if anterior else None,
            anterior_negativo=(anterior.resultado < 0) if anterior else False,
            anterior_participacion=porcentaje(anterior.participacion) if anterior else None,
            anterior_precio_medio=pesos(anterior.group.precio_medio, 2) if anterior else None,
            precio_min=pesos(cfg['precio_min'], 2),
            precio_max=pesos(cfg['precio_max'], 2),
            publicidad_max=pesos(cfg['publicidad_max']),
        )


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
        return dict(
            nombre=nombre(player),
            num_rondas=num_rondas(player.session),
            precio_medio=pesos(g.precio_medio, 2),
            demanda_total=numero(g.demanda_total),
            filas=filas_resultados(g, player),
            # Detalle propio
            ventas=pesos(player.ventas),
            costo_variable=pesos(player.costo_variable),
            costo_publicidad=pesos(player.costo_publicidad),
            costo_fijo=pesos(player.costo_fijo),
            resultado=pesos(player.resultado),
            resultado_negativo=player.resultado < 0,
        )


class ResultadoFinal(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == num_rondas(player.session)

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


page_sequence = [Instrucciones, Decision, EsperaResultados, Resultados, ResultadoFinal]
