"""
Modelo del juego de auditoría.

Funciones puras (no dependen de oTree): generan el encargo (cliente, riesgos,
controles y errores) y evalúan lo que hace cada estudio. Se prueban y calibran
con scripts/simular_auditoria.py.

El encargo
----------
- El cliente tiene 6 rubros; cada uno con su ciclo de control.
- Cada rubro tiene un RIESGO INHERENTE (bajo, medio o alto) que el equipo no ve:
  ve SEÑALES en la información del cliente, que a veces muestran un nivel vecino.
- Cada ciclo tiene un CONTROL fuerte o débil; solo se conoce si se lo prueba.
- La probabilidad de que un rubro tenga un ERROR crece con el riesgo inherente y
  con el control débil. Cada error tiene un tipo y un monto (en relación con la
  significatividad de referencia). Todos sobrevalúan el resultado.
- Cada PROCEDIMIENTO sustantivo tiene una eficacia para cada tipo de error y se
  aplica con un alcance (bajo, medio o alto) que cuesta horas. Probabilidad de
  detectar un error:  1 − Π (1 − eficacia × cobertura del alcance).
  Los números aleatorios están fijados en el escenario: la misma decisión da el
  mismo resultado en cualquier equipo, y más alcance nunca detecta menos.
- El cliente acepta cada ajuste con cierta probabilidad.
- OPINIÓN CORRECTA según lo que queda sin corregir (ajustes rechazados + errores
  no detectados) frente a la significatividad de referencia M:
      menos de M → favorable;  de M a 3M → con salvedades;  3M o más → adversa.
  Si el cliente impidió confirmar créditos y no se aplicó un procedimiento
  alternativo, la opinión correcta es la abstención.
- Si se probó el control de un ciclo y resultó fuerte, los procedimientos de ese rubro
  llevan menos horas: el auditor puede confiar en el control (NIA 330).
- PUNTAJE = honorarios − horas × costo de la hora − penalidades:
      falla de auditoría (opinión menos severa que la correcta; a la mitad si hubo
      debida diligencia: decidieron bien con lo que sabían y los errores que se escaparon
      estaban en rubros revisados con un procedimiento adecuado y el alcance que exige
      su riesgo: bajo, medio o alto),
      opinión más severa que la correcta (se pierde el cliente),
      cada rubro sin ningún procedimiento sustantivo (evidencia insuficiente).
"""
import random

# --- Rubros del cliente ---------------------------------------------------------
# saldo: en millones de pesos (se multiplica por params['escala']).
RUBROS = {
    'caja': dict(nombre='Caja y bancos', ciclo='Tesorería', saldo=40),
    'creditos': dict(nombre='Créditos por ventas', ciclo='Ventas y cobranzas', saldo=260),
    'bienes_cambio': dict(nombre='Bienes de cambio', ciclo='Inventarios', saldo=320),
    'bienes_uso': dict(nombre='Bienes de uso', ciclo='Activo fijo', saldo=280),
    'inversiones': dict(nombre='Inversiones', ciclo='Custodia de inversiones', saldo=100),
    'deudas': dict(nombre='Deudas', ciclo='Compras y pagos', saldo=380),
}
ACTIVO = ['caja', 'creditos', 'bienes_cambio', 'bienes_uso', 'inversiones']
VENTAS_BASE = 1500
RESULTADO_BASE = 120     # resultado antes de impuestos, en millones

NIVELES = ('bajo', 'medio', 'alto')

# Señales que ve el equipo en el planeamiento, según el riesgo inherente de cada rubro.
SENALES = {
    'caja': {
        'bajo': ['Los cobros son casi todos por transferencia y se depositan en el día.',
                 'La empresa maneja poco efectivo: la caja chica tiene un fondo fijo chico.'],
        'medio': ['En temporada de siembra se cobra bastante en efectivo en el mostrador.',
                  'Hay cuatro cuentas bancarias en tres bancos distintos.'],
        'alto': ['El encargado de caja no se toma vacaciones hace tres años y no deja que nadie lo reemplace.',
                 'Las conciliaciones bancarias tienen partidas pendientes de varios meses sin explicar.'],
    },
    'creditos': {
        'bajo': ['La cartera de clientes es estable y la mayoría paga a 30 días.',
                 'Las cobranzas posteriores al cierre cubren casi todos los saldos.'],
        'medio': ['Se extendieron los plazos de pago a productores por la sequía.',
                  'Hay algunos clientes con saldos vencidos de más de 90 días.'],
        'alto': ['Las ventas crecieron 40 % con los mismos clientes y en el último mes del ejercicio.',
                 'Los vendedores cobran comisión sobre lo facturado, no sobre lo cobrado.'],
    },
    'bienes_cambio': {
        'bajo': ['El inventario se cuenta todos los meses y las diferencias son mínimas.',
                 'La rotación de la mercadería es alta y no hay productos con vencimiento cercano.'],
        'medio': ['Hay mercadería en consignación en depósitos de terceros.',
                  'Algunos agroquímicos tienen vencimiento en los próximos meses.'],
        'alto': ['Este año se cambió el sistema de gestión de stock y no se hizo recuento al cierre.',
                 'Quedaron semillas de una campaña anterior que no se vendieron.'],
    },
    'bienes_uso': {
        'bajo': ['No hubo altas ni bajas importantes de bienes de uso en el ejercicio.',
                 'Las amortizaciones se calculan con el mismo sistema desde hace años.'],
        'medio': ['Se compraron dos camiones y una autoelevadora durante el ejercicio.',
                  'Se vendió un tractor usado a fin de año.'],
        'alto': ['Se renovó gran parte de la flota y no está claro qué pasó con los vehículos viejos.',
                 'El registro de bienes de uso es una planilla que lleva una sola persona.'],
    },
    'inversiones': {
        'bajo': ['Las inversiones son plazos fijos en bancos de primera línea.',
                 'Las inversiones se valúan con la cotización del último día hábil.'],
        'medio': ['Hay fondos comunes de inversión y algunos bonos.',
                  'Parte de las inversiones está en una cuenta comitente en un agente de bolsa chico.'],
        'alto': ['Se invirtió en acciones de una empresa vinculada que no cotiza.',
                 'Las inversiones se valuaron con un precio que informó la propia gerencia.'],
    },
    'deudas': {
        'bajo': ['Los proveedores son pocos y envían su estado de cuenta todos los meses.',
                 'Las compras pasan siempre por una orden de compra aprobada.'],
        'medio': ['Hay compras de urgencia que se pagan antes de recibir la factura.',
                  'Se cambió el personal de cuentas a pagar en el segundo semestre.'],
        'alto': ['La empresa necesita mostrar buenos números para renovar un crédito bancario.',
                 'Hay facturas de proveedores que llegan con mucho atraso y se registran cuando se pagan.'],
    },
}

# --- Tipos de error ---------------------------------------------------------------
ERRORES = {
    'faltante_caja': dict(rubro='caja', nombre='Faltante de fondos en caja'),
    'partida_conciliacion': dict(rubro='caja', nombre='Débitos bancarios no registrados'),
    'incobrables': dict(rubro='creditos', nombre='Créditos incobrables sin previsión'),
    'ventas_ficticias': dict(rubro='creditos', nombre='Ventas y créditos inexistentes'),
    'corte_ventas': dict(rubro='creditos', nombre='Ventas del ejercicio siguiente registradas antes del cierre'),
    'inventario_inexistente': dict(rubro='bienes_cambio', nombre='Existencias registradas que no están en el depósito'),
    'inventario_obsoleto': dict(rubro='bienes_cambio', nombre='Mercadería obsoleta valuada por encima de su valor de realización'),
    'amortizacion_omitida': dict(rubro='bienes_uso', nombre='Amortizaciones del ejercicio no registradas'),
    'bien_inexistente': dict(rubro='bienes_uso', nombre='Bienes vendidos que siguen registrados'),
    'inversion_sobrevaluada': dict(rubro='inversiones', nombre='Inversiones valuadas por encima de su valor'),
    'pasivo_omitido': dict(rubro='deudas', nombre='Facturas de proveedores no registradas'),
    'cargas_omitidas': dict(rubro='deudas', nombre='Cargas sociales devengadas no registradas'),
}

# --- Procedimientos sustantivos ---------------------------------------------------------
# horas: con alcance bajo (el medio y el alto multiplican). eficacia: por tipo de error.
PROCEDIMIENTOS = {
    'arqueo': dict(rubro='caja', nombre='Arqueo de fondos', horas=6,
                   eficacia={'faltante_caja': 0.95}),
    'conciliacion': dict(rubro='caja', nombre='Conciliación bancaria', horas=8,
                         eficacia={'partida_conciliacion': 0.95, 'faltante_caja': 0.3}),
    'confirmacion': dict(rubro='creditos', nombre='Confirmación de saldos con clientes', horas=16,
                         eficacia={'ventas_ficticias': 0.95, 'incobrables': 0.4, 'corte_ventas': 0.3}),
    'antiguedad': dict(rubro='creditos', nombre='Antigüedad de saldos y cobranzas posteriores', horas=12,
                       eficacia={'incobrables': 0.95, 'ventas_ficticias': 0.5}),
    'corte': dict(rubro='creditos', nombre='Corte de operaciones', horas=8,
                  eficacia={'corte_ventas': 0.95}),
    'observacion': dict(rubro='bienes_cambio', nombre='Observación del recuento físico', horas=16,
                        eficacia={'inventario_inexistente': 0.95, 'inventario_obsoleto': 0.5}),
    'valuacion': dict(rubro='bienes_cambio', nombre='Valuación al costo o al valor de realización', horas=10,
                      eficacia={'inventario_obsoleto': 0.95}),
    'inspeccion': dict(rubro='bienes_uso', nombre='Inspección física de bienes', horas=10,
                       eficacia={'bien_inexistente': 0.95}),
    'recalculo': dict(rubro='bienes_uso', nombre='Recálculo de amortizaciones', horas=6,
                      eficacia={'amortizacion_omitida': 0.95, 'bien_inexistente': 0.3}),
    'custodio': dict(rubro='inversiones', nombre='Confirmación con el custodio y cotizaciones', horas=6,
                     eficacia={'inversion_sobrevaluada': 0.95}),
    'pasivos_omitidos': dict(rubro='deudas', nombre='Búsqueda de pasivos omitidos (pagos posteriores al cierre)', horas=12,
                             eficacia={'pasivo_omitido': 0.95, 'cargas_omitidas': 0.4}),
    'cargas_sociales': dict(rubro='deudas', nombre='Revisión de cargas sociales', horas=6,
                            eficacia={'cargas_omitidas': 0.95}),
}

# Alcance: (nombre, multiplicador de horas, cobertura)
ALCANCES = {
    0: ('No se aplica', 0.0, 0.0),
    1: ('Bajo', 1.0, 0.35),
    2: ('Medio', 2.0, 0.70),
    3: ('Alto', 3.5, 0.95),
}

OPINIONES = ('favorable', 'salvedades', 'adversa', 'abstencion')
NOMBRES_OPINION = dict(favorable='Favorable (sin salvedades)', salvedades='Con salvedades',
                       adversa='Adversa', abstencion='Abstención de opinión')

# Probabilidad de error de un rubro según su riesgo inherente y su control.
BASE_ERROR = dict(bajo=0.05, medio=0.30, alto=0.60)
FACTOR_CONTROL = dict(fuerte=0.5, debil=2.0)

PARAMETROS = [
    'escala',                   # $ por "millón" de los saldos (1_000_000 = saldos en millones)
    'honorarios',               # $ del encargo
    'costo_hora',               # $ por hora de trabajo del estudio
    'presupuesto_horas',        # horas máximas del encargo
    'horas_planeamiento',       # horas fijas del planeamiento
    'horas_prueba_control',     # horas por cada ciclo de control probado
    'reduccion_control_fuerte', # menos horas sustantivas en rubros con control probado y fuerte (0.3 = 30 %)
    'prob_control_debil',       # probabilidad de que un ciclo tenga control débil
    'precision_senales',        # probabilidad de que la señal del planeamiento refleje el riesgo verdadero
    'factor_errores',           # multiplica la probabilidad de error (dificultad)
    'monto_min', 'monto_max',   # monto de cada error, en veces la significatividad de referencia
    'pct_significatividad',     # significatividad de referencia: % del resultado antes de impuestos
    'prob_limitacion',          # probabilidad de que el cliente no permita confirmar créditos
    'prob_acepta_ajuste',       # probabilidad de que el cliente acepte cada ajuste
    'penalidad_falla',          # en veces los honorarios: opinión menos severa que la correcta
    'factor_diligencia',        # la penalidad por falla se multiplica por esto si hubo debida diligencia
    'penalidad_severa',         # en veces los honorarios: opinión más severa que la correcta
    'penalidad_sin_evidencia',  # en veces los honorarios: por cada rubro sin procedimientos
]


# --- Escenario ----------------------------------------------------------------------

def generar_escenario(params, semilla=None):
    """El encargo: saldos, riesgos, controles, errores y los números aleatorios fijos."""
    rnd = random.Random(semilla)
    p = params
    escala = p['escala']
    saldos = {r: round(d['saldo'] * rnd.uniform(0.9, 1.1), 1) * escala for r, d in RUBROS.items()}
    resultado = round(RESULTADO_BASE * rnd.uniform(0.9, 1.1), 1) * escala
    ventas = round(VENTAS_BASE * rnd.uniform(0.95, 1.05), 1) * escala
    significatividad = p['pct_significatividad'] * resultado

    rubros = {}
    for r in RUBROS:
        riesgo = rnd.choices(NIVELES, weights=(0.40, 0.35, 0.25))[0]
        control = 'debil' if rnd.random() < p['prob_control_debil'] else 'fuerte'
        # La señal coincide con el riesgo verdadero con probabilidad `precision_senales`;
        # si no, muestra un nivel vecino (la información del cliente no es perfecta).
        nivel_senal = riesgo
        if rnd.random() >= p['precision_senales']:
            i = NIVELES.index(riesgo)
            vecinos = [NIVELES[j] for j in (i - 1, i + 1) if 0 <= j < len(NIVELES)]
            nivel_senal = rnd.choice(vecinos)
        rubros[r] = dict(riesgo=riesgo, control=control, nivel_senal=nivel_senal,
                         senal=rnd.choice(SENALES[r][nivel_senal]))

    errores = []
    for r in RUBROS:
        prob = min(0.95, BASE_ERROR[rubros[r]['riesgo']] * FACTOR_CONTROL[rubros[r]['control']] * p['factor_errores'])
        tipos = [t for t, e in ERRORES.items() if e['rubro'] == r]
        cantidad = 0
        if rnd.random() < prob:
            cantidad = 1 + (rnd.random() < prob * 0.3)
        for t in rnd.sample(tipos, min(cantidad, len(tipos))):
            monto = min(significatividad * rnd.uniform(p['monto_min'], p['monto_max']), 0.5 * saldos[r])
            errores.append(dict(
                id=f'e{len(errores) + 1}', tipo=t, rubro=r, monto=round(monto, -3),
                # Números aleatorios fijos: uno por procedimiento del rubro (detección) y uno
                # para la respuesta del cliente.
                u_deteccion={pr: rnd.random() for pr, d in PROCEDIMIENTOS.items() if d['rubro'] == r},
                u_acepta=rnd.random(),
            ))

    return dict(
        semilla=semilla, saldos=saldos, resultado=resultado, ventas=ventas,
        activo=sum(saldos[r] for r in ACTIVO),
        significatividad=significatividad,
        rubros=rubros, errores=errores,
        limitacion=rnd.random() < p['prob_limitacion'],
    )


# --- Horas -----------------------------------------------------------------------------

def horas_controles(ciclos_probados, params):
    return len(ciclos_probados) * params['horas_prueba_control']


def horas_procedimiento(proc, alcance):
    return PROCEDIMIENTOS[proc]['horas'] * ALCANCES[alcance][1]


def rubros_con_confianza(escenario, ciclos_probados):
    """Rubros cuyo control se probó y resultó fuerte: se puede confiar en él (NIA 330)."""
    if escenario is None:
        return set()
    return {r for r in ciclos_probados if escenario['rubros'][r]['control'] == 'fuerte'}


def horas_sustantivas(alcances, params=None, escenario=None, ciclos_probados=()):
    """Horas de los procedimientos. Si el control del ciclo se probó y es fuerte, las pruebas
    sustantivas de ese rubro llevan menos horas (`reduccion_control_fuerte`)."""
    confianza = rubros_con_confianza(escenario, ciclos_probados)
    total = 0.0
    for pr, a in alcances.items():
        h = horas_procedimiento(pr, a)
        if PROCEDIMIENTOS[pr]['rubro'] in confianza:
            h *= 1 - params['reduccion_control_fuerte']
        total += h
    return total


def horas_totales(ciclos_probados, alcances, params, escenario=None):
    return (params['horas_planeamiento'] + horas_controles(ciclos_probados, params)
            + horas_sustantivas(alcances, params, escenario, ciclos_probados))


def procedimientos_disponibles(escenario):
    """Con limitación al alcance, el cliente no deja confirmar saldos de créditos."""
    return [pr for pr in PROCEDIMIENTOS if not (escenario['limitacion'] and pr == 'confirmacion')]


# --- Etapas ------------------------------------------------------------------------------

def resultado_controles(escenario, ciclos_probados):
    """Lo que revelan las pruebas de controles: {rubro: 'fuerte' | 'debil'} de los ciclos probados."""
    return {r: escenario['rubros'][r]['control'] for r in ciclos_probados}


def prob_deteccion(tipo, alcances):
    """Probabilidad de detectar un error de este tipo con los alcances elegidos."""
    escapa = 1.0
    for pr, a in alcances.items():
        escapa *= 1 - PROCEDIMIENTOS[pr]['eficacia'].get(tipo, 0.0) * ALCANCES[a][2]
    return 1 - escapa


def detectados(escenario, alcances):
    """Errores encontrados: cada procedimiento aplicado lo detecta si su número fijo cae bajo
    eficacia × cobertura. Así, más alcance nunca detecta menos."""
    disponibles = set(procedimientos_disponibles(escenario))
    encontrados = []
    for e in escenario['errores']:
        for pr, u in e['u_deteccion'].items():
            a = alcances.get(pr, 0) if pr in disponibles else 0
            if a and u < PROCEDIMIENTOS[pr]['eficacia'].get(e['tipo'], 0.0) * ALCANCES[a][2]:
                encontrados.append(e)
                break
    return encontrados


def respuesta_cliente(errores_encontrados, params):
    """Ajustes que acepta el cliente: {id: True | False}."""
    return {e['id']: e['u_acepta'] < params['prob_acepta_ajuste'] for e in errores_encontrados}


def rubros_sin_evidencia(escenario, alcances):
    """Rubros sin ningún procedimiento sustantivo aplicado."""
    disponibles = set(procedimientos_disponibles(escenario))
    return [r for r in RUBROS
            if not any(alcances.get(pr, 0) for pr, d in PROCEDIMIENTOS.items() if d['rubro'] == r and pr in disponibles)]


def sin_alternativa_por_limitacion(escenario, alcances):
    return escenario['limitacion'] and not alcances.get('antiguedad', 0)


def opinion_segun(sin_corregir, significatividad):
    if sin_corregir < significatividad:
        return 'favorable'
    if sin_corregir < 3 * significatividad:
        return 'salvedades'
    return 'adversa'


def opinion_correcta(escenario, alcances, params):
    """La opinión que correspondía, con todo lo que quedó sin corregir (lo sepa o no el equipo)."""
    if sin_alternativa_por_limitacion(escenario, alcances):
        return 'abstencion'
    encontrados = detectados(escenario, alcances)
    acepta = respuesta_cliente(encontrados, params)
    ids = {e['id'] for e in encontrados}
    sin_corregir = sum(e['monto'] for e in escenario['errores'] if e['id'] not in ids or not acepta[e['id']])
    return opinion_segun(sin_corregir, escenario['significatividad'])


def opinion_conocida(escenario, alcances, params):
    """La opinión que surge solo de lo que el equipo sabe (ajustes rechazados y limitación)."""
    if sin_alternativa_por_limitacion(escenario, alcances):
        return 'abstencion'
    encontrados = detectados(escenario, alcances)
    acepta = respuesta_cliente(encontrados, params)
    rechazado = sum(e['monto'] for e in encontrados if not acepta[e['id']])
    return opinion_segun(rechazado, escenario['significatividad'])


SEVERIDAD = dict(favorable=0, salvedades=1, adversa=2)


# Alcance que exige la debida diligencia según el riesgo inherente del rubro.
ALCANCE_DILIGENTE = dict(bajo=1, medio=2, alto=3)


def revisado_con_diligencia(error, alcances, escenario):
    """El rubro del error se revisó con un procedimiento eficaz para ese tipo de error y con el alcance
    que exige su riesgo (bajo → bajo, medio → medio, alto → alto)."""
    exigido = ALCANCE_DILIGENTE[escenario['rubros'][error['rubro']]['riesgo']]
    return any(alcances.get(pr, 0) >= exigido and d['eficacia'].get(error['tipo'], 0) >= 0.9
               for pr, d in PROCEDIMIENTOS.items() if d['rubro'] == error['rubro'])


def hubo_diligencia(escenario, alcances, opinion, params):
    """Debida diligencia: la opinión no fue menos severa que lo que el estudio sabía, y cada error que se
    le escapó estaba en un rubro revisado con un procedimiento adecuado y alcance suficiente."""
    if comparar_opinion(opinion, opinion_conocida(escenario, alcances, params)) == 'falla':
        return False
    ids = {e['id'] for e in detectados(escenario, alcances)}
    return all(revisado_con_diligencia(e, alcances, escenario) for e in escenario['errores'] if e['id'] not in ids)


def comparar_opinion(elegida, correcta):
    """'correcta' | 'falla' (menos severa: se firmó algo que no correspondía) | 'severa' (más severa)."""
    if elegida == correcta:
        return 'correcta'
    if correcta == 'abstencion':
        return 'severa' if elegida == 'adversa' else 'falla'
    if elegida == 'abstencion':
        return 'severa'
    return 'falla' if SEVERIDAD[elegida] < SEVERIDAD[correcta] else 'severa'


# --- Evaluación ---------------------------------------------------------------------------

def evaluar(escenario, ciclos_probados, alcances, opinion, params):
    """Resultado completo del encargo de un estudio."""
    p = params
    horas = horas_totales(ciclos_probados, alcances, p, escenario)
    encontrados = detectados(escenario, alcances)
    ids = {e['id'] for e in encontrados}
    acepta = respuesta_cliente(encontrados, p)
    correcta = opinion_correcta(escenario, alcances, p)
    comparacion = comparar_opinion(opinion, correcta)
    sin_evidencia = rubros_sin_evidencia(escenario, alcances)
    diligente = comparacion == 'falla' and hubo_diligencia(escenario, alcances, opinion, p)

    penalidades = dict(
        falla=(p['penalidad_falla'] * p['honorarios'] * (p['factor_diligencia'] if diligente else 1.0)
               if comparacion == 'falla' else 0.0),
        severa=p['penalidad_severa'] * p['honorarios'] if comparacion == 'severa' else 0.0,
        sin_evidencia=p['penalidad_sin_evidencia'] * p['honorarios'] * len(sin_evidencia),
    )
    costo_horas = horas * p['costo_hora']
    m = escenario['significatividad']
    importantes = [e for e in escenario['errores'] if e['monto'] >= m]
    return dict(
        horas=horas,
        excede_presupuesto=horas > p['presupuesto_horas'] + 1e-9,
        costo_horas=costo_horas,
        encontrados=encontrados,
        no_detectados=[e for e in escenario['errores'] if e['id'] not in ids],
        aceptados=[e for e in encontrados if acepta[e['id']]],
        rechazados=[e for e in encontrados if not acepta[e['id']]],
        importantes=len(importantes),
        importantes_detectados=sum(1 for e in importantes if e['id'] in ids),
        sin_evidencia=sin_evidencia,
        opinion=opinion,
        opinion_correcta=correcta,
        comparacion=comparacion,
        diligente=diligente,
        penalidades=penalidades,
        puntaje=p['honorarios'] - costo_horas - sum(penalidades.values()),
    )
