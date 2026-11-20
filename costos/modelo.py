"""
Modelo del juego de costos: un taller de cortinas con dos procesos.

Funciones puras (no dependen de oTree). Se prueban y calibran con
scripts/simular_costos.py. La terminología sigue la de la cátedra de Costos
para la Gestión (FCEyJ - UNLPam).

El taller
---------
- Proceso de CORTE Y COSTURA, medido en horas hombre, y de EMBOLSADO Y TERMINADO,
  medido en horas máquina. Cada uno tiene capacidad máxima (Cm), nivel previsto (Np)
  y costos fijos de capacidad (CFC) y de operación (CFO); la tasa de costos fijos
  de cada proceso es (CFC + CFO) / Np.
- Líneas: cortinas comunes e infantiles; la línea para hoteles puede sumarse.
  Costo variable estándar de una unidad:
      tela (metros netos / rendimiento estándar × precio estándar) + accesorios
      + horas de corte × (costo de la hora de mano de obra + tasa variable de corte)
      + horas de embolsado × costo variable de la hora máquina + estuche
  y costos variables de comercialización (% del precio).
- Demanda del mes de cada línea:
      prevista a precio de referencia × (precio / precio de referencia)^(−ε) × (1 + shock)
  Se vende hasta lo que hay (stock + producción); lo que sobra queda en stock.

Costeo
------
- Variable: el producto vale su costo variable estándar; todos los costos fijos son
  del período. Resultado = contribución marginal − costos fijos − desvíos.
- Integral: además absorbe los costos fijos de los dos procesos con sus tasas.
  La diferencia entre lo absorbido y los costos fijos reales es la variación por uso
  de la capacidad. Producir de más "mejora" el resultado integral (los costos fijos
  quedan en el stock).
- Desvíos (de la producción del mes): precio de la tela, consumo (rendimiento real),
  eficiencia de la mano de obra de corte.

Eventos (uno por mes) y su informe al empresario
--------------------------------------------------
B6 pedido especial · B1 comprar o fabricar estuches · nueva línea hotelera ·
B3 eliminar la línea infantil · B5 equipo de embolsado · B4 procesamiento adicional
(bordado) · suba de la tela. Cada uno trae la decisión del mes y el número que el
equipo calcula para el informe (punto de equilibrio, de indiferencia, de cierre…).
"""
import math
import random

from nucleo.inflacion import truncada

LINEAS = {
    'comun': dict(nombre='Cortina común', precio_ref=55_000, tela_m=4.5, accesorios=2_000,
                  horas_corte=0.25, horas_embolsado=0.20, demanda=600, elasticidad=2.0,
                  cf_directos=1_000_000, cf_evitables=0, comision=0.02),
    'infantil': dict(nombre='Cortina infantil', precio_ref=48_000, tela_m=3.8, accesorios=1_800,
                     horas_corte=0.30, horas_embolsado=0.20, demanda=350, elasticidad=2.2,
                     cf_directos=1_500_000, cf_evitables=900_000, comision=0.02),
    'hotel': dict(nombre='Cortina para hoteles', precio_ref=62_000, tela_m=4.8, accesorios=2_500,
                  horas_corte=0.35, horas_embolsado=0.20, demanda=120, elasticidad=1.5,
                  cf_directos=1_200_000, cf_evitables=1_200_000, comision=0.03),
}
LINEAS_INICIALES = ('comun', 'infantil')

EVENTOS = ('pedido_especial', 'estuches', 'linea_hotel', 'competidor_infantil',
           'equipo_embolsado', 'bordado', 'suba_tela')
NOMBRES_EVENTO = dict(
    pedido_especial='Pedido especial para la Expopymes',
    estuches='Comprar o fabricar los estuches',
    linea_hotel='Nueva línea: cortinas para hoteles',
    competidor_infantil='Un competidor en cortinas infantiles',
    equipo_embolsado='Equipo de embolsado semiautomático',
    bordado='Procesamiento adicional: bordado premium',
    suba_tela='Suba del precio de la tela',
    sin_evento='Mes sin novedades',
)

PARAMETROS = [
    'precio_tela',            # $ por metro (estándar)
    'rendimiento_tela',       # rendimiento estándar de la tela (0.90 = se aprovecha el 90 %)
    'costo_hora_mo',          # $ por hora hombre de corte y costura
    'tasa_cv_corte',          # costos variables indirectos de corte, $ por hora hombre
    'cv_hora_embolsado',      # costo variable de la hora máquina de embolsado (incluye control)
    'estuche_compra',         # $ por estuche comprado
    'cm_corte', 'np_corte',   # capacidad máxima y nivel previsto de corte (horas hombre por mes)
    'cfc_corte', 'cfo_corte',
    'cm_embolsado', 'np_embolsado',
    'cfc_embolsado', 'cfo_embolsado',
    'cf_administracion', 'cf_comercializacion',
    'escala_demanda',         # multiplica la demanda de todas las líneas
    'desvio_demanda',         # desvío del shock mensual de demanda de cada línea
    'desvio_precio_tela',     # desvío mensual del precio real de la tela
    'desvio_rendimiento',     # desvío del rendimiento real de la tela (en puntos)
    'desvio_eficiencia',      # desvío de las horas reales de corte respecto del estándar
    'tolerancia_informe',     # error admitido en el informe (0.05 = ±5 %)
    'puntos_informe',         # puntos por informe acertado
    'puntos_resultado',       # puntos del ranking por el resultado
]


def tasa_corte(p):
    return (p['cfc_corte'] + p['cfo_corte']) / p['np_corte']


def tasa_embolsado(p):
    return (p['cfc_embolsado'] + p['cfo_embolsado']) / p['np_embolsado']


# --- Escenario -------------------------------------------------------------------

def generar_escenario(params, meses, semilla=None):
    """Lo común a todos los equipos: eventos, demanda prevista, shocks y condiciones reales."""
    rnd = random.Random(semilla)
    p = params
    eventos = list(EVENTOS)
    rnd.shuffle(eventos)
    eventos = (eventos + ['sin_evento'] * meses)[:meses]
    estacional = [1.0, 0.9, 1.1, 1.0, 1.2, 1.1, 0.9, 1.0, 1.1, 1.2, 1.3, 0.9]
    meses_datos = []
    for m in range(meses):
        meses_datos.append(dict(
            mes=m + 1,
            evento=eventos[m],
            factor_demanda=estacional[m % 12],
            shock={l: truncada(rnd) * p['desvio_demanda'] for l in LINEAS},
            precio_tela=p['precio_tela'] * (1 + truncada(rnd) * p['desvio_precio_tela']),
            rendimiento=p['rendimiento_tela'] + truncada(rnd) * p['desvio_rendimiento'],
            eficiencia=1 + truncada(rnd) * p['desvio_eficiencia'],
        ))
    # Datos de cada evento (sorteados: cambian si conviene o no).
    datos_eventos = dict(
        pedido_especial=dict(unidades=200, precio=rnd.choice([26_000, 29_000, 32_000, 35_000]),
                             bordado=500, cf_horas_extra=900_000, horas_extra=60),
        estuches=dict(cf=350_000, cv_propio=rnd.choice([900, 1_100, 1_300])),
        linea_hotel=dict(cf=rnd.choice([2_000_000, 3_500_000, 5_000_000]),
                         demanda=rnd.choice([60, 120, 180])),
        competidor_infantil=dict(factor=rnd.choice([0.08, 0.15, 0.3, 0.5])),
        equipo_embolsado=dict(cf=rnd.choice([350_000, 600_000, 900_000]),
                              cv_hora=rnd.choice([1_200, 1_700, 2_200]), horas=0.12),
        bordado=dict(precio_extra=7_000, cv_extra=3_000, cf=rnd.choice([900_000, 1_300_000, 1_800_000]),
                     tope=0.5),
        suba_tela=dict(suba=rnd.choice([0.10, 0.15, 0.25])),
    )
    return dict(semilla=semilla, meses=meses_datos, eventos=datos_eventos)


# --- Estado del taller de un equipo ---------------------------------------------------

def estado_inicial():
    return dict(
        lineas=list(LINEAS_INICIALES),          # líneas activas
        stock={l: 0 for l in LINEAS},           # unidades
        valor_var={l: 0.0 for l in LINEAS},     # stock a costo variable
        valor_int={l: 0.0 for l in LINEAS},     # stock a costo integral
        fabrica_estuches=False,
        equipo_semiautomatico=False,
        bordado=0.0,                            # parte de las comunes que se bordan
        suba_tela=0.0,                          # suba acumulada del precio real de la tela
        infantil_factor=1.0,                    # demanda infantil tras el competidor
        resultado_var=0.0, resultado_int=0.0,
        puntos_informe=0,
    )


def cf_directos(linea, escenario):
    if linea == 'hotel':
        return escenario['eventos']['linea_hotel']['cf']
    return LINEAS[linea]['cf_directos']


def cv_estuche(estado, escenario):
    if estado['fabrica_estuches']:
        return escenario['eventos']['estuches']['cv_propio']
    return None


def costo_variable(linea, estado, params, escenario):
    """Costo variable estándar de producción de una unidad (sin comercialización)."""
    d = LINEAS[linea]
    p = params
    tela = d['tela_m'] / p['rendimiento_tela'] * p['precio_tela']
    corte = d['horas_corte'] * (p['costo_hora_mo'] + p['tasa_cv_corte'])
    horas_emb, cv_hora = horas_embolsado(linea, estado, escenario), p['cv_hora_embolsado']
    if estado['equipo_semiautomatico']:
        cv_hora = escenario['eventos']['equipo_embolsado']['cv_hora']
    estuche = cv_estuche(estado, escenario) or p['estuche_compra']
    return tela + d['accesorios'] + corte + horas_emb * cv_hora + estuche


def horas_embolsado(linea, estado, escenario):
    if estado['equipo_semiautomatico']:
        return escenario['eventos']['equipo_embolsado']['horas']
    return LINEAS[linea]['horas_embolsado']


def costo_fijo_unitario(linea, estado, params, escenario):
    """Costos fijos de producción que absorbe una unidad en el costeo integral."""
    d = LINEAS[linea]
    return d['horas_corte'] * tasa_corte(params) + horas_embolsado(linea, estado, escenario) * tasa_embolsado(params)


def contribucion_unitaria(linea, precio, estado, params, escenario):
    return precio * (1 - LINEAS[linea]['comision']) - costo_variable(linea, estado, params, escenario)


def demanda_prevista(linea, mes, estado, params, escenario):
    """Demanda del mes a precio de referencia (lo que ve el equipo)."""
    m = escenario['meses'][mes - 1]
    base = LINEAS[linea]['demanda'] * params['escala_demanda'] * m['factor_demanda']
    if linea == 'hotel':
        base = escenario['eventos']['linea_hotel']['demanda'] * params['escala_demanda'] * m['factor_demanda']
    if linea == 'infantil':
        base *= estado['infantil_factor']
    return base


def demanda_real(linea, precio, mes, estado, params, escenario):
    d = LINEAS[linea]
    m = escenario['meses'][mes - 1]
    q = demanda_prevista(linea, mes, estado, params, escenario) * (precio / d['precio_ref']) ** (-d['elasticidad'])
    return max(0.0, q * (1 + m['shock'][linea]))


def costos_fijos_periodo(estado, params, escenario, pedido_horas_extra=False):
    """Costos fijos del mes, por concepto."""
    p = params
    ev = escenario['eventos']
    cf = dict(
        produccion=p['cfc_corte'] + p['cfo_corte'] + p['cfc_embolsado'] + p['cfo_embolsado'],
        administracion=p['cf_administracion'],
        comercializacion=p['cf_comercializacion'],
        directos=sum(cf_directos(l, escenario) for l in estado['lineas'])
        + (LINEAS['infantil']['cf_directos'] - LINEAS['infantil']['cf_evitables']
           if 'infantil' not in estado['lineas'] else 0),
        estuches=ev['estuches']['cf'] if estado['fabrica_estuches'] else 0,
        equipo=ev['equipo_embolsado']['cf'] if estado['equipo_semiautomatico'] else 0,
        bordado=ev['bordado']['cf'] if estado['bordado'] > 0 else 0,
        horas_extra=ev['pedido_especial']['cf_horas_extra'] if pedido_horas_extra else 0,
    )
    return cf


# --- Informe al empresario: el número que hay que calcular según el evento ----------------

def informe_correcto(tipo, decision, mes, estado, params, escenario):
    """(pregunta, valor correcto, unidad). Usa solo datos que el equipo ve en la pantalla."""
    ev = escenario['eventos']
    p = params
    if tipo == 'pedido_especial':
        e = ev['pedido_especial']
        cm = e['precio'] * (1 - LINEAS['comun']['comision']) - costo_variable('comun', estado, p, escenario) - e['bordado']
        return ('Contribución marginal total del pedido (sin restar las horas extra)', cm * e['unidades'], '$')
    if tipo == 'estuches':
        e = ev['estuches']
        ahorro = p['estuche_compra'] - e['cv_propio']
        return ('Punto de indiferencia entre comprar y fabricar los estuches', e['cf'] / ahorro, 'estuches por mes')
    if tipo == 'linea_hotel':
        cm = contribucion_unitaria('hotel', LINEAS['hotel']['precio_ref'], estado, p, escenario)
        return ('Punto de equilibrio de la línea para hoteles (a precio de referencia)',
                cf_directos('hotel', escenario) / cm, 'cortinas por mes')
    if tipo == 'competidor_infantil':
        cm = contribucion_unitaria('infantil', LINEAS['infantil']['precio_ref'], estado, p, escenario)
        return ('Punto de cierre de la línea infantil (a precio de referencia)',
                LINEAS['infantil']['cf_evitables'] / cm, 'cortinas por mes')
    if tipo == 'equipo_embolsado':
        e = ev['equipo_embolsado']
        ahorro = LINEAS['comun']['horas_embolsado'] * p['cv_hora_embolsado'] - e['horas'] * e['cv_hora']
        return ('Punto de indiferencia entre el equipo actual y el semiautomático', e['cf'] / ahorro, 'cortinas por mes')
    if tipo == 'bordado':
        e = ev['bordado']
        return ('Cantidad de cortinas bordadas para que el bordado esté en equilibrio',
                e['cf'] / (e['precio_extra'] - e['cv_extra']), 'cortinas por mes')
    # suba de la tela y meses sin evento: punto de equilibrio de la empresa con los precios elegidos
    return ('Punto de equilibrio de la empresa este mes, con sus precios y su mezcla prevista', None, 'cortinas por mes')


def punto_equilibrio_mezcla(precios, cantidades, estado, params, escenario, cf_total):
    """Punto de equilibrio en unidades con la mezcla de cantidades dada (contribución ponderada)."""
    total = sum(cantidades.values())
    if total <= 0:
        return None
    cm_pond = sum(cantidades[l] / total * contribucion_unitaria(l, precios[l], estado, params, escenario)
                  for l in cantidades)
    return cf_total / cm_pond if cm_pond > 0 else None


def decision_recomendada(tipo, mes, estado, params, escenario, produccion):
    """Lo que convenía decidir en el evento, con las herramientas del capítulo IV y lo que el
    equipo ve: contribución diferencial, punto de indiferencia, de equilibrio o de cierre."""
    ev = escenario['eventos']
    p = params
    volumen = sum(produccion.values())
    if tipo == 'pedido_especial':
        _, cm_total, _ = informe_correcto(tipo, None, mes, estado, p, escenario)
        horas = sum(q * LINEAS[l]['horas_corte'] for l, q in produccion.items())             + ev['pedido_especial']['unidades'] * LINEAS['comun']['horas_corte']
        extra = ev['pedido_especial']['cf_horas_extra'] if horas > p['cm_corte'] else 0
        return cm_total - extra > 0
    if tipo in ('estuches', 'equipo_embolsado'):
        _, qi, _ = informe_correcto(tipo, None, mes, estado, p, escenario)
        return volumen > qi
    if tipo == 'linea_hotel':
        pr = precio_optimo('hotel', estado, p, escenario)
        q = demanda_prevista('hotel', mes, estado, p, escenario)             * (pr / LINEAS['hotel']['precio_ref']) ** (-LINEAS['hotel']['elasticidad'])
        return q * contribucion_unitaria('hotel', pr, estado, p, escenario) > cf_directos('hotel', escenario)
    if tipo == 'competidor_infantil':
        import copy
        e = copy.deepcopy(estado)
        e['infantil_factor'] = ev['competidor_infantil']['factor']
        pr = precio_optimo('infantil', e, p, escenario)
        q = demanda_prevista('infantil', mes, e, p, escenario)             * (pr / LINEAS['infantil']['precio_ref']) ** (-LINEAS['infantil']['elasticidad'])
        return q * contribucion_unitaria('infantil', pr, e, p, escenario) < LINEAS['infantil']['cf_evitables']
    if tipo == 'bordado':
        _, qe, _ = informe_correcto(tipo, None, mes, estado, p, escenario)
        return ev['bordado']['tope'] if produccion.get('comun', 0) * ev['bordado']['tope'] > qe else 0
    return None


def acierta_informe(respuesta, correcto, params):
    if respuesta is None or correcto is None or correcto == 0:
        return False
    return abs(respuesta - correcto) <= params['tolerancia_informe'] * abs(correcto)


# --- Un mes ---------------------------------------------------------------------------------

def aplicar_decision_evento(tipo, decision, estado, escenario):
    """Efectos que rigen desde el mes del evento (o desde el siguiente)."""
    ev = escenario['eventos']
    if tipo == 'estuches' and decision:
        estado['fabrica_estuches'] = True
    elif tipo == 'equipo_embolsado' and decision:
        estado['equipo_semiautomatico'] = True
    elif tipo == 'bordado':
        estado['bordado'] = max(0.0, min(ev['bordado']['tope'], float(decision or 0)))
    elif tipo == 'suba_tela':
        estado['suba_tela'] += ev['suba_tela']['suba']


def simular_mes(mes, decisiones, estado, params, escenario):
    """
    decisiones: {precios: {linea: $}, produccion: {linea: u}, evento: valor, informe: número}
    Devuelve (nuevo estado, resultados del mes). No modifica el estado recibido.
    """
    import copy
    p = params
    est = copy.deepcopy(estado)
    m = escenario['meses'][mes - 1]
    tipo = m['evento']
    ev = escenario['eventos']
    decision = decisiones.get('evento')

    # Pregunta del informe: se calcula ANTES de aplicar la decisión del evento (con lo que ve el equipo).
    pregunta, correcto, unidad = informe_correcto(tipo, decision, mes, est, p, escenario)
    if correcto is None:
        cf_previo = sum(costos_fijos_periodo(est, p, escenario).values())
        correcto = punto_equilibrio_mezcla(decisiones['precios'], {l: decisiones['produccion'].get(l, 0) for l in est['lineas']},
                                           est, p, escenario, cf_previo)
    acierto = acierta_informe(decisiones.get('informe'), correcto, p)

    recomendada = decision_recomendada(tipo, mes, est, p, escenario,
                                       {l: decisiones['produccion'].get(l, 0) for l in est['lineas']})

    # Efectos del evento que rigen desde este mes.
    if tipo == 'competidor_infantil':
        est['infantil_factor'] = ev['competidor_infantil']['factor']
    aplicar_decision_evento(tipo, decision, est, escenario)

    # Producción y capacidad.
    produccion = {l: max(0, int(decisiones['produccion'].get(l, 0))) for l in est['lineas']}
    pedido = tipo == 'pedido_especial' and bool(decision)
    unidades_pedido = ev['pedido_especial']['unidades'] if pedido else 0
    horas_corte_std = sum(produccion[l] * LINEAS[l]['horas_corte'] for l in produccion) \
        + unidades_pedido * LINEAS['comun']['horas_corte']
    horas_emb_std = sum(produccion[l] * horas_embolsado(l, est, escenario) for l in produccion) \
        + unidades_pedido * horas_embolsado('comun', est, escenario)
    horas_extra = pedido and horas_corte_std > p['cm_corte'] + 1e-9

    # Ventas.
    filas = {}
    ventas = cm_total = cv_ventas = comisiones = 0.0
    costo_ventas_int = 0.0
    for l in est['lineas']:
        d = LINEAS[l]
        precio = float(decisiones['precios'][l])
        cv_u = costo_variable(l, est, p, escenario)
        cf_u = costo_fijo_unitario(l, est, p, escenario)
        # Bordado premium sobre una parte de las comunes: más precio y más costo variable.
        extra_precio = extra_cv = 0.0
        if l == 'comun' and est['bordado'] > 0:
            extra_precio = est['bordado'] * ev['bordado']['precio_extra']
            extra_cv = est['bordado'] * ev['bordado']['cv_extra']
        cv_u += extra_cv
        # Stock: entra la producción a costo estándar (promedio ponderado).
        q_prod = produccion[l]
        est['valor_var'][l] += q_prod * cv_u
        est['valor_int'][l] += q_prod * (cv_u + cf_u)
        disponible = est['stock'][l] + q_prod
        demanda = demanda_real(l, precio, mes, est, p, escenario)
        vendidas = min(disponible, int(round(demanda)))
        cvar_prom = est['valor_var'][l] / disponible if disponible else 0.0
        cint_prom = est['valor_int'][l] / disponible if disponible else 0.0
        precio_efectivo = precio + extra_precio
        v = vendidas * precio_efectivo
        com = v * d['comision']
        est['stock'][l] = disponible - vendidas
        est['valor_var'][l] -= vendidas * cvar_prom
        est['valor_int'][l] -= vendidas * cint_prom
        ventas += v
        comisiones += com
        cv_ventas += vendidas * cvar_prom
        costo_ventas_int += vendidas * cint_prom
        filas[l] = dict(linea=l, nombre=d['nombre'], precio=precio_efectivo, produccion=q_prod,
                        demanda=demanda, vendidas=vendidas, faltante=max(0.0, demanda - vendidas),
                        stock_final=est['stock'][l], cv_unitario=cv_u, cf_unitario=cf_u,
                        contribucion_unitaria=precio_efectivo * (1 - d['comision']) - cv_u)

    # Pedido especial: se produce y se vende aparte (comunes con bordado del logo).
    if pedido:
        e = ev['pedido_especial']
        cv_u = costo_variable('comun', est, p, escenario) + e['bordado']
        v = unidades_pedido * e['precio']
        com = v * LINEAS['comun']['comision']
        ventas += v
        comisiones += com
        cv_ventas += unidades_pedido * cv_u
        costo_ventas_int += unidades_pedido * (cv_u + costo_fijo_unitario('comun', est, p, escenario))

    # Desvíos de la producción del mes (todo lo producido, incluido el pedido).
    metros_std = sum(q * LINEAS[l]['tela_m'] / p['rendimiento_tela'] for l, q in produccion.items()) \
        + unidades_pedido * LINEAS['comun']['tela_m'] / p['rendimiento_tela']
    metros_netos = metros_std * p['rendimiento_tela']
    metros_reales = metros_netos / max(0.5, m['rendimiento'])
    precio_tela_real = m['precio_tela'] * (1 + est['suba_tela'])
    desvio_precio = (precio_tela_real - p['precio_tela']) * metros_reales
    desvio_consumo = (metros_reales - metros_std) * p['precio_tela']
    horas_reales = horas_corte_std * m['eficiencia']
    desvio_eficiencia = (horas_reales - horas_corte_std) * (p['costo_hora_mo'] + p['tasa_cv_corte'])
    desvios = dict(precio_tela=desvio_precio, consumo_tela=desvio_consumo, eficiencia_mo=desvio_eficiencia)

    cf = costos_fijos_periodo(est, p, escenario, pedido_horas_extra=horas_extra)
    cf_total = sum(cf.values())
    aplicados = horas_corte_std * tasa_corte(p) + horas_emb_std * tasa_embolsado(p)
    variacion_capacidad = cf['produccion'] - aplicados       # positivo = subaplicación (pérdida)

    contribucion = ventas - cv_ventas - comisiones
    resultado_var = contribucion - sum(desvios.values()) - cf_total
    cf_no_absorbidos = cf_total - cf['produccion']
    resultado_int = (ventas - costo_ventas_int - comisiones - sum(desvios.values())
                     - variacion_capacidad - cf_no_absorbidos)

    precios = {l: filas[l]['precio'] for l in filas}
    mezcla = {l: filas[l]['vendidas'] for l in filas}
    pe = punto_equilibrio_mezcla(precios, mezcla, est, p, escenario, cf_total)
    vendidas_total = sum(mezcla.values())
    margen_seguridad = (vendidas_total - pe) / vendidas_total if pe and vendidas_total else None

    # Línea hotelera y eliminación de la infantil rigen desde el mes siguiente.
    if tipo == 'linea_hotel' and decision and 'hotel' not in est['lineas']:
        est['lineas'].append('hotel')
    if tipo == 'competidor_infantil' and decision and 'infantil' in est['lineas']:
        est['lineas'].remove('infantil')
        # El stock que quedara se liquida a costo variable (sin resultado).
        est['stock']['infantil'] = 0
        est['valor_var']['infantil'] = est['valor_int']['infantil'] = 0.0

    est['resultado_var'] += resultado_var
    est['resultado_int'] += resultado_int
    est['puntos_informe'] += p['puntos_informe'] if acierto else 0

    resultados = dict(
        mes=mes, evento=tipo, decision=decision, recomendada=recomendada, filas=filas,
        pedido=pedido, horas_extra=horas_extra,
        horas_corte=horas_corte_std, horas_embolsado=horas_emb_std,
        ociosidad_corte=max(0.0, 1 - horas_corte_std / p['cm_corte']),
        ociosidad_embolsado=max(0.0, 1 - horas_emb_std / p['cm_embolsado']),
        ventas=ventas, cv_ventas=cv_ventas, comisiones=comisiones, contribucion=contribucion,
        costos_fijos=cf, cf_total=cf_total, desvios=desvios,
        cf_aplicados=aplicados, variacion_capacidad=variacion_capacidad,
        costo_ventas_int=costo_ventas_int,
        resultado_var=resultado_var, resultado_int=resultado_int,
        punto_equilibrio=pe, margen_seguridad=margen_seguridad,
        informe=dict(pregunta=pregunta, correcto=correcto, unidad=unidad,
                     respuesta=decisiones.get('informe'), acierto=acierto),
        stock_var=sum(est['valor_var'].values()), stock_int=sum(est['valor_int'].values()),
    )
    return est, resultados


def validar_produccion(produccion, estado, params, escenario, pedido=False):
    """None si la producción entra en la capacidad (el pedido puede usar horas extra en corte)."""
    p = params
    unidades_pedido = escenario['eventos']['pedido_especial']['unidades'] if pedido else 0
    h_corte = sum(q * LINEAS[l]['horas_corte'] for l, q in produccion.items()) + unidades_pedido * LINEAS['comun']['horas_corte']
    h_emb = sum(q * horas_embolsado(l, estado, escenario) for l, q in produccion.items()) \
        + unidades_pedido * horas_embolsado('comun', estado, escenario)
    tope_corte = p['cm_corte'] + (escenario['eventos']['pedido_especial']['horas_extra'] if pedido else 0)
    if h_corte > tope_corte + 1e-9:
        return f'Corte y costura necesita {h_corte:.0f} horas hombre y la capacidad máxima es {tope_corte:.0f}.'
    if h_emb > p['cm_embolsado'] + 1e-9:
        return f'Embolsado necesita {h_emb:.0f} horas máquina y la capacidad máxima es {p["cm_embolsado"]:.0f}.'
    return None


def puntaje_final(resultados_var, puntos_informe, params):
    """Puntos de cada equipo: resultado acumulado relativo (0 a puntos_resultado) + informes."""
    lo, hi = min(resultados_var), max(resultados_var)
    out = []
    for r, pi in zip(resultados_var, puntos_informe):
        rel = 1.0 if hi == lo else (r - lo) / (hi - lo)
        out.append(rel * params['puntos_resultado'] + pi)
    return out


def precio_optimo(linea, estado, params, escenario):
    """Precio que maximiza la contribución con demanda de elasticidad constante: cv·ε/((ε−1)(1−com))."""
    d = LINEAS[linea]
    e = d['elasticidad']
    return costo_variable(linea, estado, params, escenario) * e / ((e - 1) * (1 - d['comision']))
