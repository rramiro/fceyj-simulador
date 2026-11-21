from os import environ

SESSION_CONFIGS = [
    dict(
        name='comercializacion',
        display_name='Simulador de comercialización (gaseosas) - V3',
        app_sequence=['comercializacion'],
        num_demo_participants=4,  # una por empresa (equipo); puede ser cualquier cantidad
        # --- Desarrollo del juego ---
        num_rondas=4,  # trimestres (máximo: C.NUM_ROUNDS = 6)
        # Tamaño objetivo de cada mercado: los equipos se reparten en mercados lo más parejos
        # posible sin superarlo (ej.: 10 equipos con 4 -> mercados de 4, 3 y 3).
        empresas_por_mercado=4,
        # --- Parámetros del modelo (ver comercializacion/mercado.py) ---
        # Calibrar con: python scripts/simular_mercado.py
        # D0 del mercado = demanda_por_empresa × empresas del mercado (con 4 empresas, 40.000 u.):
        # así el negocio de cada empresa es comparable sin importar cuántas compitan.
        demanda_por_empresa=10_000,   # unidades/trimestre por empresa si todas cobran p_ref
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
    dict(
        name='cartera',
        display_name='Cartera de inversión (acciones, bonos y liquidez)',
        app_sequence=['cartera'],
        num_demo_participants=3,  # todos los equipos juegan juntos, frente al mismo mercado
        # --- Desarrollo del juego ---
        num_rondas=12,                # trimestres (máximo: C.NUM_ROUNDS = 16); informe anual cada 4
        semilla=0,                    # escenario de mercado: 0 = al azar; otro número lo repite
        # --- Parámetros del modelo (ver cartera/modelo.py) ---
        # Calibrar con: python scripts/simular_cartera.py
        capital_inicial=10_000_000,   # $ de cada equipo al empezar (todo en liquidez)
        inflacion_media=0.08,         # inflación trimestral media (8 % ≈ 36 % anual)
        inflacion_desvio=0.02,        # desvío de la inflación de cada trimestre (tope ±2 desvíos)
        acciones_media=0.02,          # rendimiento trimestral medio de las acciones en dólares (≈ 8 % anual), crisis incluidas
        acciones_desvio=0.08,         # desvío trimestral de las acciones (≈ 16 % anual)
        dolar_desvio=0.06,            # desvío trimestral del dólar respecto de la inflación
        bonos_tasa_real=0.01,         # los bonos rinden inflación + esta tasa real trimestral
        bonos_duracion=3,             # años: si la tasa real sube 1 punto, el precio cae ≈ 3 %
        bonos_desvio_tasa=0.005,      # desvío trimestral del cambio de la tasa real anual (0,5 puntos)
        liquidez_diferencial=-0.005,  # plazo fijo = inflación esperada − 0,5 % por trimestre
        prob_crisis=0.08,             # probabilidad de crisis por trimestre (≈ una cada 3 años)
        crisis_acciones=-0.20,        # en una crisis: acciones −20 % en dólares,
        crisis_dolar=0.15,            #   el dólar sube 15 % más
        crisis_bonos=-0.05,           #   y los bonos caen 5 %
        comision=0.005,               # sobre el monto comprado o vendido de acciones y bonos
        precision_noticias=0.65,      # el titular anticipa bien a las acciones 2 de cada 3 veces
        doc='Cartera de inversión: cada trimestre se reparte entre acciones internacionales, bonos y liquidez.',
    ),
    dict(
        name='auditoria',
        display_name='Auditoría de estados contables (encargo en 4 etapas)',
        app_sequence=['auditoria'],
        num_demo_participants=3,  # cada equipo es un estudio; todos auditan el mismo cliente
        semilla=0,                    # encargo: 0 = al azar; otro número lo repite
        # --- Parámetros del modelo (ver auditoria/modelo.py) ---
        # Calibrar con: python scripts/simular_auditoria.py
        escala=1_000_000,             # los saldos del cliente están en millones de pesos
        honorarios=12_000_000,        # $ del encargo
        costo_hora=20_000,            # $ por hora de trabajo del estudio
        presupuesto_horas=400,        # horas máximas del encargo
        horas_planeamiento=20,        # horas fijas del planeamiento
        horas_prueba_control=5,       # horas por cada ciclo de control probado
        reduccion_control_fuerte=0.3, # 30 % menos horas sustantivas si el control se probó y es fuerte (NIA 330)
        prob_control_debil=0.4,       # probabilidad de que un ciclo tenga control débil
        precision_senales=0.6,        # la señal del planeamiento refleja el riesgo verdadero el 60 % de las veces
        factor_errores=1.0,           # dificultad: multiplica la probabilidad de error de cada rubro
        monto_min=0.3,                # monto de cada error, en veces la significatividad de referencia
        monto_max=2.5,
        pct_significatividad=0.05,    # significatividad de referencia: 5 % del resultado antes de impuestos
        prob_limitacion=0.25,         # probabilidad de que el cliente no permita confirmar créditos
        prob_acepta_ajuste=0.7,       # probabilidad de que el cliente acepte cada ajuste
        penalidad_falla=1.0,          # en veces los honorarios: opinión menos severa que la correcta
        factor_diligencia=0.5,        # la penalidad por falla baja a la mitad si hubo debida diligencia
        penalidad_severa=0.5,         # en veces los honorarios: opinión más severa que la correcta
        penalidad_sin_evidencia=0.1,  # en veces los honorarios: por cada rubro sin procedimientos
        tolerancia_ajuste=0.01,       # error admitido al calcular un ajuste (1 %)
        bonificacion_ajuste=300_000,  # $ por cada ajuste bien calculado
        penalidad_ajuste=300_000,     # $ por cada error encontrado sin un ajuste bien calculado (re-trabajo)
        precision_relatos=0.8,        # cada rasgo del relato del control interno refleja el control real el 80 %
        prob_empresa_funcionamiento=0.3,  # probabilidad de incertidumbre sobre empresa en funcionamiento
        penalidad_enfasis=0.1,        # en veces los honorarios: omitir la sección sobre empresa en funcionamiento
        doc='Auditoría: cada equipo es un estudio que planifica, prueba controles, aplica procedimientos y emite su opinión.',
    ),
    dict(
        name='costos',
        display_name='Costos para la gestión (taller de cortinas)',
        app_sequence=['costos'],
        num_demo_participants=3,  # cada equipo maneja su taller; todos frente al mismo escenario
        num_rondas=6,                 # meses (máximo: C.NUM_ROUNDS = 12)
        semilla=0,                    # escenario: 0 = al azar; otro número lo repite
        # --- Parámetros del modelo (ver costos/modelo.py) ---
        # Calibrar con: python scripts/simular_costos.py
        precio_tela=4_000,            # $ por metro (estándar)
        rendimiento_tela=0.90,        # rendimiento estándar de la tela
        costo_hora_mo=5_120,          # $ por hora hombre de corte y costura
        tasa_cv_corte=400,            # costos variables indirectos de corte, $ por hora hombre
        cv_hora_embolsado=3_700,      # costo variable de la hora máquina de embolsado (incluye control)
        estuche_compra=1_500,         # $ por estuche comprado
        cm_corte=300, np_corte=280,   # capacidad máxima y nivel previsto de corte (horas hombre por mes)
        cfc_corte=644_000, cfo_corte=400_000,
        cm_embolsado=220, np_embolsado=200,   # embolsado (horas máquina por mes)
        cfc_embolsado=636_000, cfo_embolsado=563_400,
        cf_administracion=6_000_000,  # $ por mes
        cf_comercializacion=2_000_000,  # $ por mes (además de los costos fijos directos de cada línea)
        escala_demanda=1.0,           # multiplica la demanda de todas las líneas
        desvio_demanda=0.08,          # variación mensual de la demanda de cada línea
        desvio_precio_tela=0.04,      # variación del precio real de la tela
        desvio_rendimiento=0.015,     # variación del rendimiento real de la tela
        desvio_eficiencia=0.05,       # variación de las horas reales de corte
        tolerancia_informe=0.05,      # el informe al empresario acierta con ±5 %
        puntos_informe=5,             # puntos por informe acertado
        puntos_resultado=70,          # puntos del ranking por el resultado (relativo al mejor)
        doc='Costos: cada equipo maneja un taller de cortinas con dos procesos, decide precios, producción y un evento por mes.',
    ),
    dict(
        name='deposito',
        display_name='El depósito (gestión de inventarios)',
        app_sequence=['deposito'],
        num_demo_participants=3,  # cada equipo maneja su depósito; todos frente a la misma demanda
        num_rondas=6,                 # meses (máximo: C.NUM_ROUNDS = 12)
        semilla=0,                    # escenario: 0 = al azar; otro número lo repite
        # --- Parámetros del modelo (ver deposito/modelo.py) ---
        # Calibrar con: python scripts/simular_deposito.py
        dias_mes=25,                  # días hábiles por mes
        dias_anio=300,                # días hábiles por año (T)
        demanda_diaria=8,             # media de la demanda diaria (Poisson)
        escala_demanda=1.0,           # multiplica la demanda (dificultad)
        demora_min=2, demora_max=6,   # demora del proveedor, en días hábiles
        precio=400_000,               # ca: costo de adquisición unitario
        costo_orden=150_000,          # co: costo de emitir cada orden
        tasa_anual=0.24,              # cm = 24 % anual del precio
        costo_faltante=60_000,        # c2: margen perdido por unidad no vendida
        stock_inicial=100,
        descuento=0.03,               # descuento por cantidad (evento)
        suba_co=0.15,                 # suba de co (evento)
        suba_demanda=0.5,             # suba de la demanda en la campaña (evento)
        demora_extra_huelga=4,        # días extra de demora en la huelga (evento)
        tasa_alta=0.48,               # tasa anual durante la suba de la tasa (evento)
        tolerancia_pregunta=0.05,     # la pregunta del mes acierta con ±5 %
        puntos_pregunta=5,            # puntos por pregunta acertada
        puntos_resultado=70,          # puntos del ranking por el costo (relativo al mejor)
        doc='El depósito: cada equipo fija el lote y el punto de pedido de cada mes, con demanda y demora inciertas.',
    ),
    dict(
        name='cajas',
        display_name='Las cajas del súper (líneas de espera)',
        app_sequence=['cajas'],
        num_demo_participants=3,  # cada equipo gerencia su línea de cajas; todos con los mismos clientes
        num_rondas=8,                 # franjas: 4 por sábado (máximo: C.NUM_ROUNDS = 12)
        semilla=0,                    # escenario: 0 = al azar; otro número lo repite
        # --- Parámetros del modelo (ver cajas/modelo.py) ---
        # Calibrar con: python scripts/simular_cajas.py
        llegadas_manana=40,           # λ, clientes por hora (8 a 12 h)
        llegadas_mediodia=80,         # 12 a 14 h
        llegadas_tarde=60,            # 14 a 18 h
        llegadas_noche=100,           # 18 a 22 h
        escala_llegadas=1.0,          # multiplica todas las llegadas (dificultad)
        minutos_atencion=5,           # 1/μ: minutos por cliente en promedio (exponencial)
        costo_caja=15_000,            # Cs: $ por caja abierta y por hora
        costo_espera=20_000,          # Cc: $ por cliente y por hora en el sistema
        max_cajas=15,
        efecto_lluvia=-0.25,          # llegadas −25 % (evento)
        efecto_promocion=0.30,        # llegadas +30 % (evento)
        efecto_partido=-0.40,         # llegadas −40 %, solo de noche (evento)
        lentitud_nuevo=0.30,          # el cajero nuevo atiende 30 % más lento (evento)
        lentitud_falla=0.20,          # todas las cajas 20 % más lentas (evento)
        tolerancia_pregunta=0.05,     # la pregunta de la franja acierta con ±5 %
        puntos_pregunta=5,            # puntos por pregunta acertada
        puntos_resultado=70,          # puntos del ranking por el costo (relativo al mejor)
        doc='Las cajas del súper: cada equipo decide cuántas cajas abre en cada franja de un sábado (M/M/s).',
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
# que abre el docente (/room/aula, /room/aula2, /room/aula3). Cada aula tiene una
# sola sesión abierta a la vez, de cualquier juego: con tres aulas puede haber
# tres clases en paralelo. El docente elige el aula al crear la sesión en el tablero.
# Si se agrega una, sumarla también en _static/juegos/catalogo.json.
ROOMS = [
    dict(name='aula', display_name='Aula 1', welcome_page='global/BienvenidaAula.html'),
    dict(name='aula2', display_name='Aula 2', welcome_page='global/BienvenidaAula.html'),
    dict(name='aula3', display_name='Aula 3', welcome_page='global/BienvenidaAula.html'),
]

DEMO_PAGE_INTRO_HTML = """
<p>Simuladores de negocios de la Facultad de Ciencias Económicas y Jurídicas (UNLPam).
Elija una configuración para crear una sesión de prueba.
<a href="/static/portada/docentes.html">Volver al panel docente</a>.</p>
"""

# En el servidor se toma de la variable de entorno OTREE_SECRET_KEY (ver deploy/).
# El valor fijo solo se usa en desarrollo.
SECRET_KEY = environ.get('OTREE_SECRET_KEY', '4124799046129')
