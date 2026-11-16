from os import environ

SESSION_CONFIGS = [
    dict(
        name='comercializacion',
        display_name='Simulador de comercialización (gaseosas) - V1',
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
        # --- Límites de las decisiones ---
        precio_min=1000,              # $ por unidad
        precio_max=6000,              # $ por unidad
        publicidad_max=10_000_000,    # $ por trimestre
        doc='Mercado de gaseosas: cada empresa decide precio y publicidad por trimestre.',
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

DEMO_PAGE_INTRO_HTML = """
<p>Simulador de comercialización de la Facultad de Ciencias Económicas y Jurídicas (UNLPam).
Elija una configuración para crear una sesión de prueba.</p>
"""

SECRET_KEY = '4124799046129'
