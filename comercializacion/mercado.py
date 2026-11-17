"""
Modelo de mercado del simulador de comercialización.

Este módulo NO depende de oTree: son funciones puras que reciben las
decisiones y el estado de las empresas y los parámetros, y devuelven los
resultados. Así se pueden probar y calibrar con scripts
(ver scripts/simular_mercado.py) sin pasar por la interfaz.

Modelo (Versión 3)
------------------
0) Inflación. I_t es el índice de precios del trimestre (I = 1 en el primero).
   Todos los montos de los parámetros están en pesos del primer trimestre y
   se multiplican por I_t: costo de producción, costo fijo, almacenamiento,
   precio de referencia. Así la demanda responde al precio REAL.

1) Stock publicitario (efecto acumulado de la publicidad, en pesos reales):
       S_i = A_i / I_t + λ * S_i,anterior          (λ = retención por trimestre)

2) Precio medio del mercado (promedio simple):
       p_medio = (1/n) * Σ p_i

3) Demanda total, con estacionalidad, shock aleatorio y elasticidad:
       D = D0 * f_t * (1 + shock) * (p_medio / (p_ref * I_t)) ^ (-ε)

4) Atractivo y participación en la demanda (logit):
       a_i = -βp * (p_i / p_medio - 1) + βa * ln(1 + S_i / escala_A)
       s_i = exp(a_i) / Σ_j exp(a_j)

5) Ventas limitadas por el stock disponible (stock inicial + producción).
   La demanda no atendida pasa a las empresas con stock (ver asignar_ventas).

6) Stock valuado a precio promedio ponderado (PPP):
       costo unitario = (valor del stock inicial + producción * c * I_t)
                        / (stock inicial + producción)

7) Resultado del trimestre (criterio de costo de ventas):
       ventas - costo de ventas - publicidad - almacenamiento
       - costo financiero del stock - costo fijo - estudios de mercado
   Costo financiero = tasa del trimestre * valor del stock final.
   En el último trimestre el stock final se da de baja (pérdida = su valor).
"""

import math

# Parámetros que necesita el modelo (todos deben estar en `params`).
# Los montos están en pesos del primer trimestre (se indexan por inflación).
PARAMETROS = [
    'demanda_base',          # D0: unidades por trimestre si todas cobran p_ref (trimestre promedio)
    'precio_referencia',     # p_ref: $ por unidad
    'elasticidad',           # ε: elasticidad de la demanda total al precio medio real
    'beta_precio',           # βp: sensibilidad de la participación al precio relativo
    'beta_publicidad',       # βa: sensibilidad de la participación a la publicidad
    'escala_publicidad',     # escala_A: $ (normaliza el stock publicitario dentro del log)
    'retencion_publicidad',  # λ: fracción del stock publicitario que pasa al trimestre siguiente
    'costo_variable',        # c: $ por unidad producida
    'costo_fijo',            # $ por trimestre y por empresa
    'costo_almacenamiento',  # $ por unidad en stock al final del trimestre
    'traspaso_faltantes',    # fracción de la demanda no atendida que compra a otra empresa (0 a 1)
]


# --- Inflación ---------------------------------------------------------------

def siguiente_indice(indice_anterior, inflacion):
    return indice_anterior * (1 + inflacion)


def reexpresar(monto, indice_origen, indice_destino):
    """Lleva un monto en pesos de un trimestre a pesos de otro (moneda constante)."""
    return monto * indice_destino / indice_origen


def acumular_constante(acumulado_anterior, indice_anterior, resultado, indice):
    """Resultado acumulado en pesos del trimestre actual."""
    return reexpresar(acumulado_anterior, indice_anterior, indice) + resultado


# --- Componentes del modelo --------------------------------------------------

def stock_publicitario(publicidad, stock_anterior, retencion, indice=1.0):
    return publicidad / indice + retencion * stock_anterior


def factores_estacionales(texto):
    """Convierte '1.3, 0.9, 0.7, 1.1' en [1.3, 0.9, 0.7, 1.1]."""
    return [float(x) for x in str(texto).replace(';', ',').split(',') if x.strip()]


def trimestre_del_anio(ronda, trimestre_inicial):
    """Ronda 1, 2, ... -> trimestre del año 1..4, empezando en `trimestre_inicial`."""
    return (trimestre_inicial - 1 + ronda - 1) % 4 + 1


def precio_medio(precios):
    return sum(precios) / len(precios)


def demanda_total(p_medio, params, factor=1.0, indice=1.0):
    """`factor` agrupa estacionalidad y shock: f_t * (1 + shock)."""
    precio_real = p_medio / indice
    return factor * params['demanda_base'] * \
        (precio_real / params['precio_referencia']) ** (-params['elasticidad'])


def atractivo(precio, stock_pub, p_medio, params):
    efecto_precio = -params['beta_precio'] * (precio / p_medio - 1)
    efecto_publicidad = params['beta_publicidad'] * math.log(1 + stock_pub / params['escala_publicidad'])
    return efecto_precio + efecto_publicidad


def participaciones(atractivos):
    """Logit. Se resta el máximo para evitar desbordes numéricos (no cambia el resultado)."""
    m = max(atractivos)
    exps = [math.exp(a - m) for a in atractivos]
    total = sum(exps)
    return [e / total for e in exps]


def asignar_ventas(demandas, disponibles, partes, traspaso=1.0):
    """
    Reparte la demanda respetando el stock disponible de cada empresa.

    Cada empresa vende primero su propia demanda (hasta su stock). La demanda
    no atendida (multiplicada por `traspaso`) se ofrece a las empresas que
    todavía tienen stock, en proporción a su participación. Se repite hasta
    que no queda demanda o no queda stock.

    Devuelve (ventas, faltantes): unidades vendidas por empresa y demanda
    propia que cada una no pudo atender.
    """
    ventas = [min(d, s) for d, s in zip(demandas, disponibles)]
    faltantes = [d - v for d, v in zip(demandas, ventas)]
    pendiente = traspaso * sum(faltantes)

    for _ in range(len(demandas)):  # a lo sumo n rondas de redistribución
        con_stock = [i for i in range(len(demandas)) if disponibles[i] - ventas[i] > 1e-9]
        if pendiente <= 1e-9 or not con_stock:
            break
        peso_total = sum(partes[i] for i in con_stock)
        asignado = 0.0
        for i in con_stock:
            cuota = pendiente * partes[i] / peso_total
            toma = min(cuota, disponibles[i] - ventas[i])
            ventas[i] += toma
            asignado += toma
        pendiente -= asignado

    return ventas, faltantes


def costo_promedio(stock_inicial, valor_stock_inicial, produccion, costo_unitario_actual):
    """Costo unitario del stock disponible por precio promedio ponderado."""
    unidades = stock_inicial + produccion
    if unidades <= 0:
        return costo_unitario_actual
    return (valor_stock_inicial + produccion * costo_unitario_actual) / unidades


# --- Ronda completa ----------------------------------------------------------

def simular_ronda(decisiones, estados, params, factor_demanda=1.0, ultima_ronda=False,
                  indice=1.0, tasa_financiera=0.0):
    """
    Calcula el resultado de un trimestre para todas las empresas de un mercado.

    decisiones: lista de dicts (uno por empresa) con
        'precio', 'publicidad', 'produccion' y opcionalmente 'costo_investigacion'
        (montos nominales, en pesos del trimestre).
    estados: lista de dicts (mismo orden) con
        'stock_inicial' (unidades), 'stock_publicidad_anterior' ($ reales) y
        opcionalmente 'valor_stock_inicial' ($ nominales; si falta, se valúa
        al costo de producción del trimestre).
    params: dict con los parámetros de PARAMETROS (en pesos del primer trimestre).
    factor_demanda: estacionalidad * (1 + shock) del trimestre.
    ultima_ronda: si es True, el stock final se da de baja como pérdida.
    indice: índice de precios del trimestre (1 = primer trimestre).
    tasa_financiera: costo financiero del trimestre sobre el valor del stock final.

    Devuelve un dict con:
      'mercado': precio_medio, demanda_total, unidades_vendidas
      'empresas': lista de dicts con los resultados de cada empresa.
    """
    faltan = [k for k in PARAMETROS if k not in params]
    if faltan:
        raise KeyError(f'Faltan parámetros del modelo: {faltan}')

    c = params['costo_variable'] * indice
    pm = precio_medio([d['precio'] for d in decisiones])
    D = demanda_total(pm, params, factor_demanda, indice)

    stocks_pub = [stock_publicitario(d['publicidad'], e['stock_publicidad_anterior'],
                                     params['retencion_publicidad'], indice)
                  for d, e in zip(decisiones, estados)]
    atractivos = [atractivo(d['precio'], s, pm, params) for d, s in zip(decisiones, stocks_pub)]
    partes = participaciones(atractivos)

    demandas = [s * D for s in partes]
    disponibles = [e['stock_inicial'] + d['produccion'] for d, e in zip(decisiones, estados)]
    vendidas, faltantes = asignar_ventas(demandas, disponibles, partes, params['traspaso_faltantes'])
    total_vendidas = sum(vendidas)

    empresas = []
    for d, e, sp, s, dem, disp, u, f in zip(decisiones, estados, stocks_pub, partes,
                                            demandas, disponibles, vendidas, faltantes):
        valor_inicial = e.get('valor_stock_inicial', e['stock_inicial'] * c)
        cpp = costo_promedio(e['stock_inicial'], valor_inicial, d['produccion'], c)
        stock_final = disp - u
        valor_stock_final = stock_final * cpp

        ventas = u * d['precio']
        costo_ventas = u * cpp
        costo_publicidad = d['publicidad']
        costo_almacenamiento = stock_final * params['costo_almacenamiento'] * indice
        costo_financiero = valor_stock_final * tasa_financiera
        costo_investigacion = d.get('costo_investigacion', 0)
        costo_fijo = params['costo_fijo'] * indice
        baja_stock = valor_stock_final if ultima_ronda else 0
        resultado = (ventas - costo_ventas - costo_publicidad - costo_almacenamiento
                     - costo_financiero - costo_investigacion - costo_fijo - baja_stock)
        empresas.append(dict(
            stock_publicidad=sp,
            preferencia=s,                                   # participación en la demanda (logit)
            demanda=dem,                                     # unidades que le tocaban
            unidades=u,                                      # unidades vendidas
            faltante=f,                                      # demanda propia no atendida
            participacion=u / total_vendidas if total_vendidas else 0,  # participación en ventas
            stock_final=stock_final,
            costo_unitario=cpp,                              # costo promedio ponderado
            valor_stock_final=valor_stock_final,
            ventas=ventas,
            costo_ventas=costo_ventas,
            costo_publicidad=costo_publicidad,
            costo_almacenamiento=costo_almacenamiento,
            costo_financiero=costo_financiero,
            costo_investigacion=costo_investigacion,
            costo_fijo=costo_fijo,
            baja_stock=baja_stock,
            resultado=resultado,
        ))

    return dict(
        mercado=dict(precio_medio=pm, demanda_total=D, unidades_vendidas=total_vendidas),
        empresas=empresas,
    )


# --- Estudios de mercado -----------------------------------------------------

def pronostico_demanda(p_medio, params, factor_demanda, error_relativo, indice=1.0):
    """
    Pronóstico de la demanda total del trimestre si el precio medio es `p_medio`
    (nominal). `error_relativo` es el desvío del estudio (se sortea afuera).
    """
    return demanda_total(p_medio, params, factor_demanda, indice) * (1 + error_relativo)


def sensibilidad_precio(i, precios_propios, decisiones_rivales, estados, params, indice=1.0):
    """
    Unidades que demandarían a la empresa i para cada precio de `precios_propios`,
    si las demás eligen `decisiones_rivales` (la de i se toma de ahí para la
    publicidad) en un trimestre promedio (sin estacionalidad ni shock) y sin
    límite de stock. Precios y publicidad nominales del trimestre `indice`.
    """
    filas = []
    for p in precios_propios:
        dec = [dict(x) for x in decisiones_rivales]
        dec[i]['precio'] = p
        pm = precio_medio([d['precio'] for d in dec])
        D = demanda_total(pm, params, indice=indice)
        sp = [stock_publicitario(d['publicidad'], e['stock_publicidad_anterior'],
                                 params['retencion_publicidad'], indice)
              for d, e in zip(dec, estados)]
        partes = participaciones([atractivo(d['precio'], s, pm, params) for d, s in zip(dec, sp)])
        filas.append(dict(precio=p, unidades=partes[i] * D, participacion=partes[i]))
    return filas
