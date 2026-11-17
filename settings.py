from os import environ

SESSION_CONFIGS = [
    dict(
        name='comercializacion',
        display_name='Simulador de comercialización (gaseosas) - V3',
        app_sequence=['comercializacion'],
        num_demo_participants=4,  # una por empresa; múltiplo de PLAYERS_PER_GROUP
        # --- Desarrollo del juego ---
        num_rondas=4,  # trimestres (máximo: C.NUM_ROUNDS = 6)
        # --- Parámetros del modelo (ver comercializacion/mercado.py) ---
        # PROPUESTA INICIAL, a revisar. Calibrar con: python scripts/simular_mercado.py
        demanda_base=40_000,          # D0: unidades/trimestre del mercado si todas cobran p_ref
        precio_referencia=2500,       # p_ref: $ por unidad
        elasticidad=1.5,              # ε: elasticidad de la demanda total al precio medio (>1)
        beta_precio=2.2,            # βp: sensibilidad de la participación al precio relativo
        beta_publicidad=0.3,          # βa: sensibilidad de la participación a la publicidad
        escala_publicidad=500_000,    # $: inversión a partir de la cual la publicidad "se nota"
        costo_variable=1200,          # $ por unidad
        costo_fijo=6_000_000,         # $ por trimestre y por empresa
        # --- V2: publicidad acumulada ---
        retencion_publicidad=0.5,     # λ: parte del stock publicitario que pasa al trimestre siguiente
        # --- V2: producción y stock ---
        capacidad=20_000,             # unidades máximas a producir por trimestre
        stock_inicial=0,              # unidades en stock al empezar el juego
        costo_almacenamiento=100,     # $ por unidad en stock al cierre de cada trimestre (sin incluir el costo financiero)
        traspaso_faltantes=1.0,       # parte de la demanda no atendida que compra a otra empresa (0 a 1)
        # --- V2: demanda variable ---
        estacionalidad='1.3, 0.9, 0.7, 1.1',  # factores por trimestre del año (ene-mar = verano); promedian 1
        trimestre_inicial=1,          # trimestre del año en que empieza el juego (1 = ene-mar)
        desvio_shock=0.05,            # desvío del shock aleatorio de demanda (5 %)
        # --- V3: contexto argentino ---
        # Los montos de esta configuración están en pesos del primer trimestre y se indexan.
        inflacion_media=0.08,         # inflación trimestral media (8 % ≈ 36 % anual)
        inflacion_desvio=0.02,        # desvío de la inflación de cada trimestre (tope ±2 desvíos)
        tasa_real=0.02,               # tasa real trimestral; costo financiero del stock = inflación + tasa real
        # --- V2: investigación de mercado ---
        costo_estudio_competencia=400_000,   # datos de los rivales del trimestre anterior
        costo_estudio_pronostico=400_000,    # pronóstico de demanda del trimestre
        costo_estudio_sensibilidad=600_000,  # unidades propias a distintos precios
        error_pronostico=0.05,        # el pronóstico puede errar hasta ±5 %
        # --- Límites de las decisiones ---
        precio_min=1000,              # $ por unidad
        precio_max=6000,              # $ por unidad
        publicidad_max=10_000_000,    # $ por trimestre
        doc='Mercado de gaseosas: cada empresa decide precio, publicidad y producción por trimestre.',
    ),
]

# if you set a property in SESSION_CONFIG_DEFAULTS, it will be inherited by all configs
# in SESSION_CONFIGS, except those that explicitly override it.
# the session config can be accessed from methods in your apps as self.session.config,
# e.g. self.session.config['participation_fee']

SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=1.00, participation_fee=0.00, doc=""
)

PARTICIPANT_FIELDS = []
SESSION_FIELDS = []

# ISO-639 code
# for example: de, fr, ja, ko, zh-hans
LANGUAGE_CODE = 'es'

# e.g. EUR, GBP, CNY, JPY
REAL_WORLD_CURRENCY_CODE = 'ARS'
USE_POINTS = True

ADMIN_USERNAME = 'admin'
# for security, best to set admin password in an environment variable
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD')

# Aulas ("rooms" de oTree): enlace fijo por el que los equipos entran a la sesión
# que abre el docente. Los alumnos usan /room/aula; el docente crea la sesión
# desde /room_without_session/aula (o Rooms en el panel).
ROOMS = [
    dict(
        name='aula',
        display_name='Aula de la FCEyJ',
        welcome_page='global/BienvenidaAula.html',
    ),
]

DEMO_PAGE_INTRO_HTML = """
<p>Simulador de comercialización de la Facultad de Ciencias Económicas y Jurídicas (UNLPam).
Elija una configuración para crear una sesión de prueba.
<a href="/static/portada/docentes.html">Volver al panel docente</a>.</p>
"""

# En el servidor se toma de la variable de entorno OTREE_SECRET_KEY (ver deploy/).
# El valor fijo solo se usa en desarrollo.
SECRET_KEY = environ.get('OTREE_SECRET_KEY', '4124799046129')
