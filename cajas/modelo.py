"""
Modelo del juego "Las cajas del súper" (Métodos Cuantitativos para la Administración, unidades 4 y 5).

Funciones puras (no dependen de oTree). Se prueban y calibran con scripts/simular_cajas.py.

Notación de la cátedra (teórico de líneas de espera, guía 2025 unidad 4)
-----------------------------------------------------------------------
    λ   velocidad media de llegada (clientes por hora)     s    cantidad de cajas (canales)
    μ   velocidad media de servicio de una caja            r    λ / μ
    ρ   utilización = λ / (s·μ)                            P0   probabilidad de sistema vacío
    Lq  clientes promedio en la fila                       Ls   clientes promedio en el sistema = Lq + r
    Wq  espera promedio en la fila = Lq / λ                Ws   tiempo promedio en el sistema = Wq + 1/μ
    Pw  probabilidad de tener que esperar (Erlang C)
    Cs  costo de una caja abierta por hora                 Cc   costo de espera por cliente y hora en el sistema

    Costo total por hora:  CT(s) = Cs·s + Cc·Ls(s)

El juego
--------
- Súper Quantum, un sábado de 8 a 22 en cuatro franjas (mañana, mediodía, tarde, noche); cada franja es una
  ronda. Se juegan uno o más sábados.
- Fila única (M/M/s): llegadas Poisson y tiempo de atención exponencial. Las llegadas y el "trabajo" de cada
  cliente están sorteados en el escenario: todos los equipos atienden a los mismos clientes.
- El equipo decide cuántas cajas abre en la franja. Si cierra cajas, cada cajero termina el cliente que atiende.
  Los clientes que siguen en el súper al terminar la franja pasan a la siguiente; a las 22 se cierran las
  puertas y se atiende a los que quedaron adentro.
- Costo de la franja = Cs · cajas · horas + Cc · (horas-cliente en el sistema, en fila o en caja).
- Un evento por franja (anunciado antes de decidir): lluvia, promoción, cajero nuevo, falla del sistema de cobro,
  partido de fútbol o franja normal.
- Pregunta de la franja: una medida del modelo M/M/s (ρ, Ls, Lq, Wq, Pw, s óptimo).
"""
import copy
import heapq
import math
import random

FRANJAS = [
    # nombre, hora de inicio, horas, llegadas por hora (base)
    dict(nombre='Mañana', inicio=8, horas=4, clave='llegadas_manana'),
    dict(nombre='Mediodía', inicio=12, horas=2, clave='llegadas_mediodia'),
    dict(nombre='Tarde', inicio=14, horas=4, clave='llegadas_tarde'),
    dict(nombre='Noche', inicio=18, horas=4, clave='llegadas_noche'),
]

EVENTOS = {
    'normal': 'Franja normal',
    'lluvia': 'Lluvia',
    'promocion': 'Promoción en la radio',
    'cajero_nuevo': 'Cajero nuevo',
    'falla': 'Falla del sistema de cobro',
    'partido': 'Partido de fútbol',
}

PARAMETROS = [
    'llegadas_manana', 'llegadas_mediodia', 'llegadas_tarde', 'llegadas_noche',   # λ por hora
    'escala_llegadas',      # multiplica todas las llegadas (dificultad)
    'minutos_atencion',     # 1/μ en minutos
    'costo_caja',           # Cs por caja y hora
    'costo_espera',         # Cc por cliente y hora en el sistema
    'max_cajas',
    'efecto_lluvia',        # −0.25: llegadas −25 %
    'efecto_promocion',     # +0.30
    'efecto_partido',       # −0.40 (solo de noche)
    'lentitud_nuevo',       # 0.30: el cajero nuevo atiende 30 % más lento
    'lentitud_falla',       # 0.20: todas las cajas 20 % más lentas
    'tolerancia_pregunta',
    'puntos_pregunta', 'puntos_resultado',
]


def franja_de_ronda(ronda):
    """(sábado, índice de franja 0..3) de la ronda 1, 2, ..."""
    return (ronda - 1) // len(FRANJAS) + 1, (ronda - 1) % len(FRANJAS)


# --- Escenario -------------------------------------------------------------------------

def generar_escenario(params, rondas, semilla=None):
    """Eventos, llegadas y trabajo de cada cliente, por ronda (iguales para todos los equipos).
    Las llegadas se sortean para la λ con el evento ya aplicado; el trabajo es exponencial de media 1
    (el tiempo de atención es trabajo · minutos de la caja)."""
    rnd = random.Random(semilla)
    eventos = []
    tipos = ['lluvia', 'promocion', 'cajero_nuevo', 'falla']
    bolsa = []
    for r in range(1, rondas + 1):
        sabado, f = franja_de_ronda(r)
        # La primera franja de todo el juego es normal, para aprender sin sorpresas.
        if r == 1 or rnd.random() < 0.3:
            eventos.append('normal')
            continue
        opciones = tipos + (['partido'] if f == 3 else [])
        if not bolsa:
            bolsa = rnd.sample(tipos, len(tipos))
        tipo = 'partido' if f == 3 and rnd.random() < 0.35 else bolsa.pop()
        eventos.append(tipo if tipo in opciones else 'normal')
    datos = []
    for r in range(1, rondas + 1):
        d = datos_ronda(r, params, dict(eventos=eventos))
        minutos = d['horas'] * 60
        llegadas, t = [], 0.0
        while True:
            t += rnd.expovariate(d['lam'] / 60)
            if t >= minutos:
                break
            llegadas.append(round(t, 3))
        datos.append(dict(llegadas=llegadas, trabajo=[round(rnd.expovariate(1), 4) for _ in llegadas]))
    return dict(semilla=semilla, eventos=eventos, rondas=datos)


# --- Datos de la ronda y fórmulas M/M/s -----------------------------------------------------

def datos_ronda(ronda, params, escenario):
    p = params
    sabado, f = franja_de_ronda(ronda)
    fr = FRANJAS[f]
    ev = escenario['eventos'][ronda - 1]
    lam = p[fr['clave']] * p['escala_llegadas']
    if ev == 'lluvia':
        lam *= 1 + p['efecto_lluvia']
    elif ev == 'promocion':
        lam *= 1 + p['efecto_promocion']
    elif ev == 'partido':
        lam *= 1 + p['efecto_partido']
    minutos = p['minutos_atencion'] * (1 + p['lentitud_falla'] if ev == 'falla' else 1)
    return dict(
        sabado=sabado, franja=f, nombre=fr['nombre'], inicio=fr['inicio'], horas=fr['horas'],
        evento=ev, lam=lam, minutos=minutos, mu=60 / minutos,
        cs=p['costo_caja'], cc=p['costo_espera'],
    )


def mms(lam, mu, s):
    """Medidas del modelo M/M/s (por hora). None si el sistema no es estable (ρ ≥ 1)."""
    if s < 1 or lam <= 0:
        return None
    r = lam / mu
    rho = r / s
    if rho >= 1:
        return None
    suma = sum(r ** n / math.factorial(n) for n in range(s))
    cola = r ** s / (math.factorial(s) * (1 - rho))
    p0 = 1 / (suma + cola)
    pw = p0 * cola
    lq = pw * rho / (1 - rho)
    wq = lq / lam
    return dict(rho=rho, p0=p0, pw=pw, lq=lq, ls=lq + r, wq=wq, ws=wq + 1 / mu)


def costo_hora(lam, mu, s, cs, cc):
    """CT(s) = Cs·s + Cc·Ls(s); None si es inestable."""
    m = mms(lam, mu, s)
    return None if m is None else cs * s + cc * m['ls']


def cajas_optimas(lam, mu, cs, cc, max_cajas):
    costos = [(costo_hora(lam, mu, s, cs, cc), s) for s in range(1, max_cajas + 1)]
    costos = [(c, s) for c, s in costos if c is not None]
    return min(costos)[1] if costos else max_cajas


def formulas(ronda, params, escenario):
    """Valores del modelo para la ronda: s óptimo y sus medidas, s mínimo estable y la curva de costo."""
    d = datos_ronda(ronda, params, escenario)
    s_opt = cajas_optimas(d['lam'], d['mu'], d['cs'], d['cc'], int(params['max_cajas']))
    curva = []
    for s in range(1, int(params['max_cajas']) + 1):
        m = mms(d['lam'], d['mu'], s)
        curva.append(dict(s=s, estable=m is not None,
                          costo=None if m is None else d['cs'] * s + d['cc'] * m['ls'],
                          wq_min=None if m is None else m['wq'] * 60, rho=d['lam'] / (s * d['mu'])))
    return dict(s_opt=s_opt, s_min=math.floor(d['lam'] / d['mu']) + 1,
                medidas=mms(d['lam'], d['mu'], s_opt), curva=curva, r=d['lam'] / d['mu'])


# --- Pregunta de la ronda -----------------------------------------------------------------------

def pregunta_de_la_ronda(ronda, params, escenario):
    """(pregunta, valor correcto, unidad). Las medidas se piden para s = cajas óptimas del modelo; salvo
    en la rotación, que también pide el s óptimo."""
    d = datos_ronda(ronda, params, escenario)
    f = formulas(ronda, params, escenario)
    s = f['s_opt']
    m = f['medidas']
    lam = f'λ = {d["lam"]:.0f} clientes/h'
    ev = d['evento']
    if ev == 'falla':
        return (f'Con la falla cada caja atiende en {d["minutos"]:.1f} min. Con {lam} y s = {s} cajas, '
                'calcule la utilización ρ', m['rho'], '(entre 0 y 1)')
    if ev in ('lluvia', 'partido'):
        return (f'Con {lam}, ¿cuántas cajas minimizan el costo total por hora CT = Cs·s + Cc·Ls?', s, 'cajas')
    if ev == 'promocion':
        return (f'Con {lam} y s = {s} cajas, calcule el tiempo medio de espera en la fila Wq', m['wq'] * 60,
                'minutos')
    rotacion = [
        (f'Con {lam} y s = {s} cajas, calcule la utilización ρ', m['rho'], '(entre 0 y 1)'),
        (f'Con {lam} y s = {s} cajas, calcule la cantidad media de clientes en el sistema Ls (en fila o en caja)',
         m['ls'], 'clientes'),
        (f'Con {lam} y s = {s} cajas, calcule la cantidad media de clientes en la fila Lq', m['lq'], 'clientes'),
        (f'Con {lam} y s = {s} cajas, calcule la probabilidad de que un cliente tenga que esperar', m['pw'],
         '(entre 0 y 1)'),
        (f'Con {lam}, ¿cuántas cajas minimizan el costo total por hora CT = Cs·s + Cc·Ls?', s, 'cajas'),
        (f'Con {lam} y s = {s} cajas, calcule el tiempo medio de espera en la fila Wq', m['wq'] * 60, 'minutos'),
    ]
    k = sum(1 for e in escenario['eventos'][:ronda] if e in ('normal', 'cajero_nuevo'))
    return rotacion[(k - 1) % len(rotacion)]


def acierta(respuesta, correcto, params):
    if respuesta is None:
        return False
    return abs(respuesta - correcto) <= params['tolerancia_pregunta'] * max(abs(correcto), 1e-9) + 1e-9


# --- Simulación de la ronda ----------------------------------------------------------------------

def estado_inicial(params):
    # en_sistema: clientes que siguen en el súper al empezar la ronda.
    #   [minuto de llegada relativo a la ronda (≤ 0), trabajo restante, caja (None si en fila), fin de atención]
    return dict(fila=[], en_caja=[], costo_acumulado=0.0, aciertos=0, sabado=1)


def simular_ronda(ronda, cajas, estado, params, escenario):
    """Simula la franja con `cajas` abiertas. Devuelve (estado nuevo, resultados).

    Eventos discretos: llegadas sorteadas, fila única FIFO, primera caja libre. El cajero nuevo (evento) es
    la caja 1. Si es la última franja del sábado, a la hora de cierre no entran más clientes y se atiende a
    los que quedaron; ese tiempo extra suma espera pero no horas de caja."""
    p = params
    est = copy.deepcopy(estado)
    d = datos_ronda(ronda, params, escenario)
    sabado, f = franja_de_ronda(ronda)
    if sabado != est.get('sabado', 1):
        # Sábado nuevo: el súper abre vacío.
        est['fila'], est['en_caja'], est['sabado'] = [], [], sabado
    datos = escenario['rondas'][ronda - 1]
    cajas = max(1, min(int(cajas), int(p['max_cajas'])))
    minutos = d['horas'] * 60
    ultima = f == len(FRANJAS) - 1

    def minutos_caja(caja):
        lento = 1 + p['lentitud_nuevo'] if d['evento'] == 'cajero_nuevo' and caja == 0 else 1
        return d['minutos'] * lento

    # Estado de las cajas: libre_desde[c] = minuto en que se libera (≤ 0 si libre).
    libre = [0.0] * max(cajas, int(p['max_cajas']))
    abiertas = set(range(cajas))
    # Los que estaban en caja al terminar la ronda anterior siguen en su caja (aunque se haya cerrado).
    clientes = []   # dict(llega, inicio, fin)
    for c in est['en_caja']:
        caja = c['caja']
        fin = c['resta']   # minutos restantes, relativo al comienzo de esta ronda
        libre[caja] = fin
        clientes.append(dict(llega=c['llega'], inicio=c['inicio'], fin=fin, previo=True, caja=caja))
    fila = [dict(llega=c['llega'], trabajo=c['trabajo'], previo=True) for c in est['fila']]
    fila += [dict(llega=t, trabajo=w, previo=False) for t, w in zip(datos['llegadas'], datos['trabajo'])]

    # Atención FIFO: cada cliente toma la caja abierta que se libera primero (las cerradas no toman nuevos).
    # Al cerrar la franja (si no es la última), los que no empezaron pasan a la siguiente.
    heap = [(max(0.0, libre[c]), c) for c in abiertas]
    heapq.heapify(heap)
    pendientes = []
    for cli in fila:
        t_libre, c = heap[0]
        inicio = max(t_libre, cli['llega'])
        if inicio >= minutos and not ultima:
            pendientes.append(cli)
            continue
        heapq.heappop(heap)
        fin = inicio + cli['trabajo'] * minutos_caja(c)
        heapq.heappush(heap, (fin, c))
        clientes.append(dict(llega=cli['llega'], inicio=inicio, fin=fin, previo=cli['previo'], caja=c))
    # Los que pasan a la ronda siguiente: en caja (empezaron y no terminaron) o en fila.
    en_caja_sig = [dict(llega=c['llega'] - minutos, inicio=c['inicio'] - minutos, resta=c['fin'] - minutos,
                        caja=c['caja'])
                   for c in clientes if not ultima and c['inicio'] < minutos < c['fin']]
    fila_sig = [dict(llega=c['llega'] - minutos, trabajo=c['trabajo']) for c in pendientes]

    # Horas-cliente en el sistema durante la franja (en la última, hasta que sale el último).
    tope = max([minutos] + [c['fin'] for c in clientes]) if ultima else minutos
    horas_cliente = sum(min(c['fin'], tope) - max(c['llega'], 0) for c in clientes) / 60
    horas_cliente += sum(minutos - max(c['llega'], 0) for c in pendientes) / 60
    atendidos = [c for c in clientes if c['fin'] <= tope and not c['previo']]
    nuevos = [c for c in clientes if not c['previo']]
    esperas = [c['inicio'] - c['llega'] for c in nuevos]
    # Utilización observada: tiempo de atención dentro de la franja / (cajas · minutos).
    ocupado = sum(max(0.0, min(c['fin'], minutos) - max(c['inicio'], 0)) for c in clientes)

    # Serie minuto a minuto: clientes en la fila y en caja.
    serie = []
    paso = 5 if d['horas'] >= 4 else 2
    for t in range(0, int(tope) + 1, paso):
        en_fila = sum(1 for c in clientes if c['llega'] <= t < c['inicio']) + \
            sum(1 for c in pendientes if c['llega'] <= t)
        atendiendo = sum(1 for c in clientes if c['inicio'] <= t < c['fin'])
        serie.append(dict(minuto=t, fila=en_fila, caja=atendiendo))

    costo_cajas = d['cs'] * cajas * d['horas']
    costo_espera = d['cc'] * horas_cliente
    costo = costo_cajas + costo_espera
    est['fila'], est['en_caja'] = fila_sig, en_caja_sig
    est['costo_acumulado'] += costo
    lam_obs = len(datos['llegadas']) / d['horas']
    return est, dict(
        ronda=ronda, sabado=sabado, franja=f, nombre=d['nombre'], evento=d['evento'], cajas=cajas,
        llegaron=len(datos['llegadas']), atendidos=len(atendidos), quedan=len(fila_sig) + len(en_caja_sig),
        lam_observada=lam_obs,
        rho_observada=ocupado / (cajas * minutos),
        ls_observada=horas_cliente / d['horas'],
        lq_observada=sum(esperas) / 60 / d['horas'] if esperas else 0.0,
        wq_observada=sum(esperas) / len(esperas) if esperas else 0.0,
        espera_max=max(esperas) if esperas else 0.0,
        pw_observada=sum(1 for e in esperas if e > 1e-9) / len(esperas) if esperas else 0.0,
        fila_max=max(x['fila'] for x in serie), cierre_extra=max(0.0, tope - minutos),
        serie=serie, costo_cajas=costo_cajas, costo_espera=costo_espera, costo=costo,
    )


def cajas_recomendadas(ronda, params, escenario):
    """La decisión "de manual": el s que minimiza CT(s) en el modelo M/M/s con los datos de la franja."""
    return formulas(ronda, params, escenario)['s_opt']


def puntaje_final(costos, puntos_pregunta, params):
    """Puntos: costo acumulado relativo (menor costo = puntos_resultado) + preguntas acertadas."""
    lo, hi = min(costos), max(costos)
    return [(1.0 if hi == lo else (hi - c) / (hi - lo)) * params['puntos_resultado'] + pp
            for c, pp in zip(costos, puntos_pregunta)]
