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
- Cada error encontrado trae su PAPEL DE TRABAJO (arqueo, conciliación, recuento,
  circularización…) con los datos para calcular el AJUSTE. El estudio carga el monto;
  si está bien calculado (± tolerancia), el cliente lo acepta con cierta probabilidad;
  si no, lo devuelve y el error queda sin corregir.
- Cada ciclo de control trae un RELATO de dos rasgos (como el TP 3 de la cátedra) que
  refleja el control verdadero con probabilidad `precision_relatos`. El estudio califica
  el control; probarlo lo confirma.
- EMPRESA EN FUNCIONAMIENTO (evento): a veces hay una incertidumbre significativa,
  revelada en notas; el informe debe incluir la sección que la menciona (RT 37 mod.
  por la RT 53).
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
      cada rubro sin ningún procedimiento sustantivo (evidencia insuficiente),
      omitir la sección sobre empresa en funcionamiento cuando correspondía,
      cada error encontrado sin un ajuste bien calculado (re-trabajo con el cliente);
  más una bonificación por cada ajuste bien calculado.
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
# Lenguaje de la RT 37 modificada por la RT 53.
NOMBRES_OPINION = dict(favorable='Opinión favorable (no modificada)', salvedades='Opinión con salvedades',
                       adversa='Opinión adversa', abstencion='Abstención de opinión')
EXPLICACION_OPINION = dict(
    favorable='lo que queda sin corregir no es significativo',
    salvedades='lo que queda sin corregir es significativo, pero no generalizado',
    adversa='lo que queda sin corregir es significativo y generalizado (3 veces la significatividad o más)',
    abstencion='no se obtuvieron elementos de juicio suficientes sobre un rubro importante',
)

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
    'tolerancia_ajuste',        # error admitido al calcular un ajuste (0.01 = 1 %)
    'bonificacion_ajuste',      # $ por cada ajuste bien calculado
    'penalidad_ajuste',         # $ por cada error encontrado sin un ajuste bien calculado (re-trabajo con el cliente)
    'precision_relatos',        # probabilidad de que cada rasgo del relato refleje el control verdadero
    'prob_empresa_funcionamiento',  # probabilidad de incertidumbre sobre empresa en funcionamiento
    'penalidad_enfasis',        # en veces los honorarios: omitir la sección sobre empresa en funcionamiento
]

# --- Relatos del control interno (estilo TP 3 de la cátedra) -------------------------------
# Rasgos de cada ciclo según su control. El relato muestra dos; cada uno refleja el control
# verdadero con probabilidad `precision_relatos`.
RELATOS = {
    'caja': {
        'fuerte': ['Las cobranzas se depositan íntegras al día siguiente y los pagos se hacen por transferencia.',
                   'La conciliación bancaria la hace una persona que no maneja fondos, todos los meses.',
                   'El fondo fijo tiene acta de creación y se arquea por sorpresa.'],
        'debil': ['El mismo empleado cobra, deposita y registra los movimientos de caja.',
                  'Cuando el gerente viaja deja cheques firmados en blanco para las urgencias.',
                  'Hace meses que no se concilian las cuentas bancarias.'],
    },
    'creditos': {
        'fuerte': ['Los créditos a clientes nuevos los aprueba Créditos y Cobranzas con un límite escrito.',
                   'Las notas de crédito y los descuentos tienen una política escrita y los autoriza la gerencia.',
                   'Contaduría compara todos los meses el mayor de deudores con las fichas de los clientes.'],
        'debil': ['Los vendedores aprueban el crédito de sus propios clientes.',
                  'Los descuentos no tienen política: se "charlan" con el dueño.',
                  'Las cobranzas las recibe el mismo empleado que lleva las cuentas de los clientes.'],
    },
    'bienes_cambio': {
        'fuerte': ['El inventario permanente se coteja con recuentos rotativos y se investigan las diferencias.',
                   'El depósito solo entrega mercadería con remito numerado y firmado.',
                   'Las recepciones se registran con informe de recepción numerado.'],
        'debil': ['El encargado del depósito registra las entradas y salidas y también hace los recuentos.',
                  'Se despacha mercadería con remitos sin numerar cuando hay apuro.',
                  'No hay seguimiento de la mercadería vencida o de baja rotación.'],
    },
    'bienes_uso': {
        'fuerte': ['Las compras de bienes de uso las aprueba el directorio y quedan en acta.',
                   'Hay un registro de bienes con número de inventario que se controla una vez al año.',
                   'Las bajas y ventas de bienes necesitan autorización escrita.'],
        'debil': ['Los vehículos viejos se venden sin autorización y sin avisar a Contaduría.',
                  'No hay registro de bienes: solo las facturas de compra.',
                  'Las mejoras se registran como gastos "para pagar menos impuestos".'],
    },
    'inversiones': {
        'fuerte': ['Los títulos están en custodia en un agente con extractos mensuales que concilia Contaduría.',
                   'Las inversiones las decide un comité con dos firmas.',
                   'Las valuaciones usan cotizaciones del mercado del último día hábil.'],
        'debil': ['El gerente financiero decide, opera y registra las inversiones él solo.',
                  'No se piden extractos al agente de bolsa.',
                  'Las acciones que no cotizan se valúan con un precio que estima la gerencia.'],
    },
    'deudas': {
        'fuerte': ['Toda compra tiene orden de compra aprobada, informe de recepción y factura que se cotejan.',
                   'Los proveedores envían su estado de cuenta y se concilia todos los meses.',
                   'Los pagos los autoriza una persona distinta de la que registra las facturas.'],
        'debil': ['Las facturas se registran recién cuando se pagan.',
                  'Hay compras de urgencia sin orden de compra.',
                  'Nadie concilia los saldos con los proveedores.'],
    },
}
CALIFICACIONES_CONTROL = dict(confio='Confío en el control', no_confio='No confío en el control')


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
        **_extras(rnd, rubros, errores, ventas, p),
    )


def _extras(rnd, rubros, errores, ventas, p):
    """Lo que se sortea después del resto (así los escenarios anteriores no cambian): relatos del
    control interno, datos de los papeles de trabajo, empresa en funcionamiento y datos legales."""
    for r, d in rubros.items():
        otro = 'debil' if d['control'] == 'fuerte' else 'fuerte'
        niveles = [d['control'] if rnd.random() < p['precision_relatos'] else otro for _ in range(2)]
        primero = rnd.choice(RELATOS[r][niveles[0]])
        segundo = rnd.choice([x for x in RELATOS[r][niveles[1]] if x != primero])
        d['relato'] = [primero, segundo]
    for e in errores:
        e['semilla_papel'] = rnd.randrange(10 ** 9)
    return dict(
        empresa_funcionamiento=rnd.random() < p['prob_empresa_funcionamiento'],
        legales=dict(sipa=round(ventas * rnd.uniform(0.008, 0.012), -3),
                     iibb=round(ventas * rnd.uniform(0.002, 0.004), -3)),
    )


# --- Papeles de trabajo y ajustes -------------------------------------------------------------
# Cada error encontrado trae los datos que reunió el procedimiento, armados como en los
# prácticos de la cátedra. El ajuste correcto es siempre el monto del error.

def _linea(concepto, importe=None, texto=None):
    return dict(concepto=concepto, importe=importe, texto=texto)


def _divisor(rnd, x, opciones):
    """Un divisor de x entre las opciones (x es múltiplo de 1.000)."""
    validas = [d for d in opciones if x % d == 0]
    return rnd.choice(validas or [1000])


def papel_de_trabajo(error):
    """Datos del procedimiento que encontró el error y la pregunta del ajuste."""
    rnd = random.Random(error.get('semilla_papel', 0))
    x = int(error['monto'])
    t = error['tipo']
    redondo = lambda v: int(round(v, -3))   # noqa: E731

    if t == 'faltante_caja':
        efectivo = redondo(x * rnd.uniform(0.3, 0.8))
        gastos = redondo(x * rnd.uniform(0.05, 0.15))
        anticipo = redondo(x * rnd.uniform(0.05, 0.2))
        proveedor = redondo(x * rnd.uniform(0.1, 0.3))
        saldo = x + efectivo + gastos + anticipo + proveedor
        return dict(procedimiento='Arqueo de fondos al cierre', lineas=[
            _linea('Saldo contable de Caja', saldo),
            _linea('Recuento: dinero en efectivo', efectivo),
            _linea('Recuento: comprobantes de gastos de limpieza', gastos),
            _linea('Recuento: vale por anticipo de sueldo', anticipo),
            _linea('Recuento: recibo de pago a un proveedor', proveedor),
        ], nota='Los comprobantes son válidos y se reimputan a sus cuentas; lo que no se justifica es faltante.',
            pregunta='Faltante de caja (diferencia sin justificar)')

    if t == 'partida_conciliacion':
        intereses = redondo(x * rnd.uniform(0.02, 0.08))
        rechazado = redondo(x * rnd.uniform(0.3, 0.6))
        gastos = x + intereses - rechazado
        cheques = redondo(x * rnd.uniform(0.5, 1.5))
        depositos = redondo(x * rnd.uniform(0.3, 1.0))
        libros = redondo(x * rnd.uniform(3, 6))
        banco = libros - x - depositos + cheques
        return dict(procedimiento='Conciliación bancaria al cierre', lineas=[
            _linea('Saldo según libros', libros),
            _linea('Saldo según resumen bancario', banco),
            _linea('Cheques emitidos y entregados, no debitados', cheques),
            _linea('Depósito del último día, no acreditado', depositos),
            _linea('Notas de débito por gastos e impuestos bancarios, no contabilizadas', gastos),
            _linea('Cheque de cliente depositado y rechazado, no contabilizado', rechazado),
            _linea('Nota de crédito por intereses, no contabilizada', intereses),
        ], nota='Separen las partidas temporales (no se ajustan) de las que requieren registración.',
            pregunta='Ajuste neto a registrar: disminución de Banco')

    if t == 'incobrables':
        pct = rnd.choice([0.4, 0.5, 0.6])
        previsto = redondo(x * rnd.uniform(0, 0.3))
        saldo = int(round((x + previsto) / (1 - pct)))
        return dict(procedimiento='Antigüedad de saldos y circularización', lineas=[
            _linea('Saldo de Distribuidora del Valle S.R.L. (en concurso preventivo)', saldo),
            _linea('Porcentaje que se estima cobrar según el abogado', texto=f'{pct * 100:.0f} %'),
            _linea('Previsión ya constituida para este deudor', previsto),
        ], nota='La previsión debe cubrir lo que no se espera cobrar.',
            pregunta='Previsión a constituir (cargo a resultados)')

    if t == 'ventas_ficticias':
        transito = redondo(x * rnd.uniform(0.2, 0.6))
        confirmado = redondo(x * rnd.uniform(1, 3))
        libros = confirmado + transito + x
        return dict(procedimiento='Circularización de saldos de clientes', lineas=[
            _linea('Saldo de Cooperativa Agrícola Limitada según libros', libros),
            _linea('Saldo que confirma el cliente', confirmado),
            _linea('Pago del cliente del 30/6, recibido por la empresa el 2/7', transito),
            _linea('Facturas que el cliente no reconoce (sin remito firmado)', texto='ver diferencia'),
        ], nota='El pago en tránsito es una diferencia de cobranza, no de ventas.',
            pregunta='Ventas y créditos inexistentes a anular')

    if t == 'corte_ventas':
        unidades = _divisor(rnd, x, (100, 125, 200, 250, 500))
        costo = rnd.choice(range(20_000, 60_001, 1000))
        precio = costo + x // unidades
        return dict(procedimiento='Corte de operaciones', lineas=[
            _linea('Factura 0003-00004127 del 30/6: unidades', texto=f'{unidades}'),
            _linea('Precio de venta unitario facturado', precio),
            _linea('Costo unitario registrado', costo),
            _linea('Remito de esa factura', texto='despachado el 3/7 (ejercicio siguiente)'),
            _linea('Factura 0003-00004126 del 30/6 con remito del 30/6', texto='correcta'),
        ], nota='Una venta se reconoce cuando se entrega la mercadería.',
            pregunta='Efecto en el resultado de anular la venta (ventas menos costo)')

    if t == 'inventario_inexistente':
        faltan = _divisor(rnd, x, (20, 25, 40, 50, 100, 125, 200))
        costo = x // faltan
        registradas = faltan + rnd.randint(50, 300)
        otro = rnd.randint(100, 500)
        return dict(procedimiento='Observación del recuento físico', lineas=[
            _linea('Bolsas de fertilizante: según inventario permanente', texto=f'{registradas} unidades'),
            _linea('Bolsas de fertilizante: recontadas', texto=f'{registradas - faltan} unidades'),
            _linea('Costo unitario de las bolsas', costo),
            _linea('Bidones de herbicida: según inventario y recontados', texto=f'{otro} unidades (coinciden)'),
        ], nota='No hay remitos ni informes de recepción pendientes que expliquen la diferencia.',
            pregunta='Faltante de inventario a ajustar (a costo)')

    if t == 'inventario_obsoleto':
        unidades = _divisor(rnd, x, (50, 100, 125, 200, 250))
        vnr = 9 * rnd.randint(1000, 5000)
        precio = vnr * 10 // 9
        costo = vnr + x // unidades
        return dict(procedimiento='Valuación al costo o al valor neto de realización', lineas=[
            _linea('Semillas de la campaña anterior: unidades', texto=f'{unidades}'),
            _linea('Costo unitario registrado', costo),
            _linea('Precio de venta estimado', precio),
            _linea('Gastos directos de venta', texto='10 % del precio'),
        ], nota='Los bienes de cambio no pueden superar su valor neto de realización.',
            pregunta='Desvalorización a registrar')

    if t == 'amortizacion_omitida':
        vida = rnd.choice([5, 10])
        meses = rnd.choice([6, 12])
        origen = x * vida * 12 // meses
        return dict(procedimiento='Recálculo de amortizaciones', lineas=[
            _linea('Autoelevadora: valor de origen', origen),
            _linea('Vida útil', texto=f'{vida} años, amortización lineal por meses de uso'),
            _linea('Meses de uso en el ejercicio', texto=f'{meses}'),
            _linea('Amortización registrada en el ejercicio', 0),
        ], nota='El resto de los bienes se amortizó correctamente.',
            pregunta='Amortización del ejercicio a registrar')

    if t == 'bien_inexistente':
        origen = x * rnd.choice([2, 3, 4])
        acumulada = origen - x
        return dict(procedimiento='Inspección física de bienes', lineas=[
            _linea('Camión Ford 2016 (no se encontró; se vendió en marzo): valor de origen', origen),
            _linea('Amortización acumulada', acumulada),
            _linea('Precio de la venta', texto='registrado como "otros ingresos"'),
        ], nota='El camión sigue en el activo. Calculen el valor residual que hay que dar de baja.',
            pregunta='Valor residual a dar de baja (pérdida a reconocer)')

    if t == 'inversion_sobrevaluada':
        cantidad = _divisor(rnd, x, (500, 1000))
        cotizacion = 100 * rnd.randint(20, 200)
        neto = cotizacion - cotizacion // 100
        valor_libros = neto + x // cantidad
        return dict(procedimiento='Confirmación con el custodio y cotizaciones', lineas=[
            _linea('Acciones de Pampa Energía en cartera', texto=f'{cantidad}'),
            _linea('Valor por acción según libros', valor_libros),
            _linea('Cotización al cierre por acción', cotizacion),
            _linea('Gastos directos de venta', texto='1 % de la cotización'),
        ], nota='Se valúan a cotización neta de gastos directos de venta.',
            pregunta='Desvalorización de las inversiones')

    if t == 'pasivo_omitido':
        enero = redondo(x * rnd.uniform(0.3, 1.0))
        registrada = redondo(x * rnd.uniform(0.3, 1.0))
        return dict(procedimiento='Búsqueda de pasivos omitidos: pagos posteriores al cierre', lineas=[
            _linea('Pago del 5/7 a Agroquímica Sur: factura del 20/6, no registrada', x),
            _linea('Pago del 8/7 a Transportes del Oeste: factura del 3/7', enero),
            _linea('Pago del 10/7 a Semillera Pampeana: factura del 25/6, registrada en Proveedores', registrada),
        ], nota='Solo corresponde al ejercicio lo devengado hasta el cierre.',
            pregunta='Pasivo omitido a registrar')

    if t == 'cargas_omitidas':
        tasa = rnd.choice([0.20, 0.25])
        sueldos = int(round(x / tasa))
        aportes = redondo(sueldos * 0.17)
        return dict(procedimiento='Revisión de cargas sociales', lineas=[
            _linea('Sueldos devengados de junio', sueldos),
            _linea('Aportes retenidos al personal (17 %), registrados', aportes),
            _linea('Contribuciones patronales', texto=f'{tasa * 100:.0f} % de los sueldos, no registradas'),
        ], nota='Las contribuciones a cargo del empleador se devengan con los sueldos.',
            pregunta='Contribuciones patronales a registrar')

    raise ValueError(t)


def ajuste_correcto(error, monto, params):
    """El ajuste cargado coincide con el monto del error, con la tolerancia de la sesión."""
    return monto is not None and abs(monto - error['monto']) <= params['tolerancia_ajuste'] * error['monto'] + 1


def estado_ajuste(error, montos, params):
    """'aceptado' | 'rechazado' (bien calculado, el cliente no lo registra) |
    'devuelto' (mal calculado) | 'sin_proponer'. Sin `montos`, se supone bien calculado."""
    if montos is not None:
        monto = montos.get(error['id'])
        if monto is None:
            return 'sin_proponer'
        if not ajuste_correcto(error, monto, params):
            return 'devuelto'
    return 'aceptado' if error['u_acepta'] < params['prob_acepta_ajuste'] else 'rechazado'


def evaluacion_control(escenario, calificaciones):
    """Ciclos bien calificados: 'confio' con control fuerte o 'no_confio' con control débil."""
    return sum(1 for r, c in (calificaciones or {}).items()
               if (c == 'confio') == (escenario['rubros'][r]['control'] == 'fuerte'))



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


def respuesta_cliente(errores_encontrados, params, montos=None):
    """Ajustes que quedan registrados: {id: True | False}. Solo los bien calculados que el cliente acepta."""
    return {e['id']: estado_ajuste(e, montos, params) == 'aceptado' for e in errores_encontrados}


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


def opinion_correcta(escenario, alcances, params, montos=None):
    """La opinión que correspondía, con todo lo que quedó sin corregir (lo sepa o no el equipo)."""
    if sin_alternativa_por_limitacion(escenario, alcances):
        return 'abstencion'
    encontrados = detectados(escenario, alcances)
    acepta = respuesta_cliente(encontrados, params, montos)
    ids = {e['id'] for e in encontrados}
    sin_corregir = sum(e['monto'] for e in escenario['errores'] if e['id'] not in ids or not acepta[e['id']])
    return opinion_segun(sin_corregir, escenario['significatividad'])


def opinion_conocida(escenario, alcances, params, montos=None):
    """La opinión que surge solo de lo que el equipo sabe (ajustes no registrados y limitación)."""
    if sin_alternativa_por_limitacion(escenario, alcances):
        return 'abstencion'
    encontrados = detectados(escenario, alcances)
    acepta = respuesta_cliente(encontrados, params, montos)
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


def hubo_diligencia(escenario, alcances, opinion, params, montos=None):
    """Debida diligencia: la opinión no fue menos severa que lo que el estudio sabía, y cada error que se
    le escapó estaba en un rubro revisado con un procedimiento adecuado y alcance suficiente."""
    if comparar_opinion(opinion, opinion_conocida(escenario, alcances, params, montos)) == 'falla':
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

def evaluar(escenario, ciclos_probados, alcances, opinion, params, montos=None, enfasis=None):
    """Resultado completo del encargo de un estudio. `montos`: ajustes cargados {id: $} (None = todos bien
    calculados). `enfasis`: si incluyó la sección sobre empresa en funcionamiento (None = lo que corresponda)."""
    p = params
    horas = horas_totales(ciclos_probados, alcances, p, escenario)
    encontrados = detectados(escenario, alcances)
    ids = {e['id'] for e in encontrados}
    estados = {e['id']: estado_ajuste(e, montos, p) for e in encontrados}
    acepta = {i: v == 'aceptado' for i, v in estados.items()}
    correcta = opinion_correcta(escenario, alcances, p, montos)
    comparacion = comparar_opinion(opinion, correcta)
    sin_evidencia = rubros_sin_evidencia(escenario, alcances)
    diligente = comparacion == 'falla' and hubo_diligencia(escenario, alcances, opinion, p, montos)
    hay_ef = escenario.get('empresa_funcionamiento', False)
    if enfasis is None:
        enfasis = hay_ef
    bien_calculados = sum(1 for v in estados.values() if v in ('aceptado', 'rechazado'))

    penalidades = dict(
        falla=(p['penalidad_falla'] * p['honorarios'] * (p['factor_diligencia'] if diligente else 1.0)
               if comparacion == 'falla' else 0.0),
        severa=p['penalidad_severa'] * p['honorarios'] if comparacion == 'severa' else 0.0,
        sin_evidencia=p['penalidad_sin_evidencia'] * p['honorarios'] * len(sin_evidencia),
        enfasis=p['penalidad_enfasis'] * p['honorarios'] if hay_ef and not enfasis else 0.0,
        ajustes=p['penalidad_ajuste'] * (len(encontrados) - bien_calculados),
    )
    bonificacion = bien_calculados * p['bonificacion_ajuste']
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
        rechazados=[e for e in encontrados if estados[e['id']] == 'rechazado'],
        devueltos=[e for e in encontrados if estados[e['id']] in ('devuelto', 'sin_proponer')],
        estados=estados,
        bien_calculados=bien_calculados,
        bonificacion=bonificacion,
        empresa_funcionamiento=hay_ef,
        enfasis=enfasis,
        importantes=len(importantes),
        importantes_detectados=sum(1 for e in importantes if e['id'] in ids),
        sin_evidencia=sin_evidencia,
        opinion=opinion,
        opinion_correcta=correcta,
        comparacion=comparacion,
        diligente=diligente,
        penalidades=penalidades,
        puntaje=p['honorarios'] - costo_horas - sum(penalidades.values()) + bonificacion,
    )
