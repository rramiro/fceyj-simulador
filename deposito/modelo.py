"""
Modelo del juego "El depósito" (Métodos Cuantitativos para la Administración, unidad 3).

Funciones puras (no dependen de oTree). Se prueban y calibran con scripts/simular_deposito.py.

Notación de la cátedra
----------------------
    D   demanda del período (unidades por año)        T   período (1 año = `dias_anio` días hábiles)
    n   tamaño del lote                                h   cantidad de órdenes = D / n
    ca  costo de adquisición unitario                  t   intervalo entre órdenes = T / h
    co  costo de cada orden                            sp  stock de protección
    cm  costo de mantener una unidad en el período     R   punto de pedido = demanda en la demora + sp
    c2  costo de cada unidad faltante (venta perdida)

    n0 = √(2·co·D / (cm·T))          CT0 (gestión) = √(2·co·D·cm·T)          (+ ca·D si se cuenta la compra)

El juego
--------
- Cada mes tiene `dias_mes` días hábiles. La demanda diaria es Poisson con la media del mes; la demora
  del proveedor es uniforme entre `demora_min` y `demora_max` días (enteros). Todo está sorteado en el
  escenario, igual para todos los equipos: la k-ésima orden del mes usa la k-ésima demora sorteada.
- Política del equipo (revisión continua): cada día, si la posición (stock + pedidos en camino) queda
  en R o menos, se pide un lote n. El pedido llega al comenzar el día de llegada.
- Lo que no hay en stock se pierde (venta perdida) y cuesta c2 por unidad.
- Mantener cuesta cm por unidad y por día sobre el stock al cerrar cada día.
- Un evento por mes (sorteado): descuento por cantidad (en una sola orden del mes, la primera de n ≥ umbral;
  nunca en los dos últimos meses), suba de co, campaña de ventas (demanda +50 %),
  huelga del proveedor (más demora), suba de la tasa (más cm) o mes normal.
- COSTO DE GESTIÓN = órdenes + mantenimiento + faltantes − ahorro por descuentos. La compra ca·D no
  entra (es la misma para todos), salvo el ahorro del descuento.
- Pregunta del mes: un número que el equipo calcula con las fórmulas del modelo (n0, CT0, h0, t0, R…).
"""
import copy
import math
import random

EVENTOS = {
    'normal': 'Mes normal',
    'descuento': 'Descuento por cantidad',
    'suba_co': 'Aumento del costo de emitir órdenes',
    'campania': 'Campaña de ventas',
    'huelga': 'Huelga en el transporte del proveedor',
    'tasa': 'Suba de la tasa de interés',
}

PARAMETROS = [
    'dias_mes',             # días hábiles por mes
    'dias_anio',            # días hábiles por año (T)
    'demanda_diaria',       # media de la demanda diaria (Poisson)
    'escala_demanda',       # multiplica la demanda (dificultad)
    'demora_min', 'demora_max',   # demora del proveedor, en días hábiles
    'precio',               # ca: costo de adquisición unitario
    'costo_orden',          # co
    'tasa_anual',           # cm = tasa_anual · ca / dias_anio por unidad y día
    'costo_faltante',       # c2 por unidad no vendida
    'stock_inicial',
    'descuento',            # descuento por cantidad (0.10 = 10 %)
    'suba_co',              # suba de co en el evento (0.15 = 15 %)
    'suba_demanda',         # suba de la demanda en la campaña (0.5 = 50 %)
    'demora_extra_huelga',  # días que se suman a la demora en la huelga
    'tasa_alta',            # tasa anual durante el evento de suba de la tasa
    'tolerancia_pregunta',  # error admitido en la pregunta del mes
    'puntos_pregunta', 'puntos_resultado',
]

MAX_ORDENES_MES = 60


def _poisson(rnd, media):
    """Poisson por el método de Knuth (medias chicas, como las de este juego)."""
    if media <= 0:
        return 0
    if media > 60:
        return max(0, round(rnd.gauss(media, math.sqrt(media))))
    limite, k, prod = math.exp(-media), 0, rnd.random()
    while prod > limite:
        k += 1
        prod *= rnd.random()
    return k


# --- Escenario -------------------------------------------------------------------------

def generar_escenario(params, meses, semilla=None):
    """Eventos, demanda diaria y demoras de cada mes (iguales para todos los equipos)."""
    rnd = random.Random(semilla)
    p = params
    tipos = [t for t in EVENTOS if t != 'normal']
    sorteo = rnd.sample(tipos, len(tipos)) * 3
    eventos = []
    for m in range(meses):
        # El primer mes es normal; después, cada evento una vez antes de repetir, con algún mes normal.
        if m == 0 or rnd.random() < 0.2:
            eventos.append(dict(tipo='normal'))
            continue
        tipo = sorteo.pop(0)
        # El descuento no cae en los dos últimos meses: lo comprado con descuento al final no se llegaría
        # a mantener (el juego termina) y el ahorro sería gratis.
        if tipo == 'descuento' and m >= meses - 2:
            tipo = sorteo.pop(0) if sorteo[0] != 'descuento' else 'normal'
        eventos.append(dict(tipo=tipo))
    for e in eventos:
        if e['tipo'] == 'descuento':
            e['umbral'] = rnd.choice([150, 300, 600, 1000])
    meses_datos = []
    for m in range(meses):
        media = p['demanda_diaria'] * p['escala_demanda'] * (1 + p['suba_demanda'] if eventos[m]['tipo'] == 'campania' else 1)
        meses_datos.append(dict(
            demanda=[_poisson(rnd, media) for _ in range(p['dias_mes'])],
            u_demora=[rnd.random() for _ in range(MAX_ORDENES_MES)],
        ))
    return dict(semilla=semilla, eventos=eventos, meses=meses_datos)


# --- Parámetros del mes y fórmulas de la cátedra ------------------------------------------

def datos_mes(mes, params, escenario):
    """Parámetros vigentes en el mes (con el evento aplicado)."""
    p = params
    ev = escenario['eventos'][mes - 1]
    precio = p['precio']
    tasa = p['tasa_alta'] if ev['tipo'] == 'tasa' else p['tasa_anual']
    co = p['costo_orden'] * (1 + p['suba_co'] if ev['tipo'] == 'suba_co' else 1)
    media = p['demanda_diaria'] * p['escala_demanda'] * (1 + p['suba_demanda'] if ev['tipo'] == 'campania' else 1)
    extra = p['demora_extra_huelga'] if ev['tipo'] == 'huelga' else 0
    return dict(
        evento=ev['tipo'], umbral=ev.get('umbral'),
        precio=precio, co=co, tasa=tasa,
        cm_dia=tasa * precio / p['dias_anio'],
        c2=p['costo_faltante'],
        media_diaria=media,
        D=media * p['dias_anio'],
        demora_min=p['demora_min'] + extra, demora_max=p['demora_max'] + extra,
    )


def lote_optimo(co, D, cm_anual):
    """n0 = √(2·co·D / (cm·T)), con cm por unidad y por año (T = 1)."""
    return math.sqrt(2 * co * D / cm_anual)


def costo_gestion_anual(n, co, D, cm_anual):
    """Costo anual de ordenar y mantener con lote n (modelo sin agotamiento): co·D/n + ½·n·cm·T."""
    return co * D / n + 0.5 * n * cm_anual


def formulas(mes, params, escenario):
    """Los valores del modelo de la cátedra para el mes: n0, CT0, h0, t0, R y sp de referencia."""
    d = datos_mes(mes, params, escenario)
    cm_anual = d['cm_dia'] * params['dias_anio']
    n0 = lote_optimo(d['co'], d['D'], cm_anual)
    demora_media = (d['demora_min'] + d['demora_max']) / 2
    r_media = d['media_diaria'] * demora_media
    r_max = d['media_diaria'] * d['demora_max']
    return dict(
        n0=n0, ct0=math.sqrt(2 * d['co'] * d['D'] * cm_anual), h0=d['D'] / n0,
        t0=params['dias_anio'] * n0 / d['D'], cm_anual=cm_anual,
        demanda_demora_media=r_media, demanda_demora_max=r_max, sp=r_max - r_media,
    )


def conviene_descuento(mes, params, escenario):
    """Costo anual total (compra + órdenes + mantener) con n0 sin descuento y con el umbral con descuento.
    Con descuento baja ca y, como cm es un % de ca, también cm (Quantum Carbono, ej. 5.1)."""
    d = datos_mes(mes, params, escenario)
    if d['evento'] != 'descuento':
        return None
    f = formulas(mes, params, escenario)
    sin = d['precio'] * d['D'] + costo_gestion_anual(f['n0'], d['co'], d['D'], f['cm_anual'])
    precio_desc = d['precio'] * (1 - params['descuento'])
    cm_desc = f['cm_anual'] * (1 - params['descuento'])
    n_desc = max(d['umbral'], lote_optimo(d['co'], d['D'], cm_desc))
    con = precio_desc * d['D'] + costo_gestion_anual(n_desc, d['co'], d['D'], cm_desc)
    return dict(sin=sin, con=con, ahorro=sin - con, n_desc=n_desc)


# --- Pregunta del mes -----------------------------------------------------------------------

def pregunta_del_mes(mes, params, escenario):
    """(pregunta, valor correcto, unidad)."""
    d = datos_mes(mes, params, escenario)
    f = formulas(mes, params, escenario)
    ev = d['evento']
    if ev == 'descuento':
        c = conviene_descuento(mes, params, escenario)
        return (f'Ahorro anual (compra + órdenes + mantenimiento) de pedir {d["umbral"]} unidades con el descuento '
                'en lugar del lote óptimo sin descuento (negativo si no conviene)', c['ahorro'], '$ por año')
    if ev == 'suba_co':
        return ('Nuevo lote óptimo n0 con el aumento del costo de emitir órdenes', f['n0'], 'unidades')
    if ev == 'campania':
        return ('Lote óptimo n0 con la demanda de la campaña', f['n0'], 'unidades')
    if ev == 'huelga':
        return ('Punto de pedido R que cubre la demora máxima de la huelga sin faltantes (demanda media × demora máxima)',
                f['demanda_demora_max'], 'unidades')
    if ev == 'tasa':
        return ('Costo anual de gestión CT0 = √(2·co·D·cm·T) con la nueva tasa', f['ct0'], '$ por año')
    # Mes normal: se rota entre las fórmulas básicas.
    rotacion = [
        ('Lote óptimo n0 = √(2·co·D / (cm·T))', f['n0'], 'unidades'),
        ('Cantidad de órdenes por año h0 = D / n0', f['h0'], 'órdenes'),
        ('Intervalo entre órdenes t0 = T / h0', f['t0'], 'días hábiles'),
        ('Costo anual de gestión CT0 = √(2·co·D·cm·T)', f['ct0'], '$ por año'),
        ('Stock de protección sp para cubrir la demora máxima (demanda media × (demora máxima − demora media))',
         f['sp'], 'unidades'),
    ]
    normales = [m for m in range(1, mes + 1) if escenario['eventos'][m - 1]['tipo'] == 'normal']
    return rotacion[(len(normales) - 1) % len(rotacion)]


def acierta(respuesta, correcto, params):
    if respuesta is None:
        return False
    return abs(respuesta - correcto) <= params['tolerancia_pregunta'] * max(abs(correcto), 1)


# --- Simulación del mes ------------------------------------------------------------------------

def estado_inicial(params):
    return dict(stock=params['stock_inicial'], en_camino=[], costo_acumulado=0.0, aciertos=0)


def simular_mes(mes, lote, punto_pedido, estado, params, escenario):
    """Simula el mes día por día con la política (n, R). Devuelve (estado nuevo, resultados).
    `en_camino`: lista de [día de llegada relativo al inicio del mes, unidades]."""
    p = params
    est = copy.deepcopy(estado)
    d = datos_mes(mes, params, escenario)
    datos = escenario['meses'][mes - 1]
    dias = p['dias_mes']
    lote = max(1, int(lote))
    punto_pedido = max(0, int(punto_pedido))
    con_descuento = d['evento'] == 'descuento' and lote >= d['umbral']

    stock = est['stock']
    en_camino = [list(x) for x in est['en_camino']]
    serie = []
    ordenes = []
    vendidas = perdidas = 0
    mantener = 0.0
    for dia in range(dias):
        # Llegan los pedidos al comenzar el día.
        llegan = sum(u for (dl, u) in en_camino if dl <= dia)
        en_camino = [[dl, u] for (dl, u) in en_camino if dl > dia]
        stock += llegan
        demanda = datos['demanda'][dia]
        venta = min(stock, demanda)
        stock -= venta
        vendidas += venta
        perdidas += demanda - venta
        mantener += stock * d['cm_dia']
        # Revisión al cerrar el día: si la posición está en R o menos, se pide n.
        posicion = stock + sum(u for _, u in en_camino)
        while posicion <= punto_pedido and len(ordenes) < MAX_ORDENES_MES:
            u = datos['u_demora'][len(ordenes)]
            demora = d['demora_min'] + int(u * (d['demora_max'] - d['demora_min'] + 1))
            en_camino.append([dia + 1 + demora, lote])
            ordenes.append(dict(dia=dia + 1, llega=dia + 1 + demora, unidades=lote))
            posicion += lote
        serie.append(dict(dia=dia + 1, stock=stock, demanda=demanda, faltante=demanda - venta, llegan=llegan))

    costo_ordenes = len(ordenes) * d['co']
    costo_faltantes = perdidas * d['c2']
    # El descuento vale para una sola orden del mes (la primera, si el lote alcanza el umbral).
    ahorro = lote * d['precio'] * p['descuento'] if con_descuento and ordenes else 0.0
    costo = costo_ordenes + mantener + costo_faltantes - ahorro

    est['stock'] = stock
    # Lo que sigue en camino pasa al mes siguiente (días relativos al nuevo mes).
    est['en_camino'] = [[dl - dias, u] for (dl, u) in en_camino]
    est['costo_acumulado'] += costo
    return est, dict(
        mes=mes, evento=d['evento'], lote=lote, punto_pedido=punto_pedido,
        serie=serie, ordenes=ordenes, vendidas=vendidas, perdidas=perdidas,
        demanda=sum(datos['demanda']),
        costo_ordenes=costo_ordenes, costo_mantener=mantener, costo_faltantes=costo_faltantes,
        ahorro_descuento=ahorro, con_descuento=con_descuento, costo=costo,
        stock_final=stock, stock_promedio=sum(x['stock'] for x in serie) / dias,
        nivel_servicio=vendidas / max(1, vendidas + perdidas),
    )


def politica_recomendada(mes, params, escenario):
    """La política "de manual": n0 (o el umbral del descuento si conviene) y R = demanda media × demora máxima."""
    d = datos_mes(mes, params, escenario)
    f = formulas(mes, params, escenario)
    n = f['n0']
    if d['evento'] == 'descuento':
        c = conviene_descuento(mes, params, escenario)
        if c['ahorro'] > 0:
            n = c['n_desc']
    return round(n), math.ceil(f['demanda_demora_max'])


def puntaje_final(costos, puntos_pregunta, params):
    """Puntos: costo acumulado relativo (menor costo = puntos_resultado) + preguntas acertadas."""
    lo, hi = min(costos), max(costos)
    return [(1.0 if hi == lo else (hi - c) / (hi - lo)) * params['puntos_resultado'] + pp
            for c, pp in zip(costos, puntos_pregunta)]
