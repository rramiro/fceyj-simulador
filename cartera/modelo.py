"""
Modelo del juego de cartera de inversión.

Funciones puras (no dependen de oTree): generan el escenario de mercado de la
sesión y calculan la evolución de una cartera. Se prueban y calibran con
scripts/simular_cartera.py sin pasar por la interfaz.

Modelo (por trimestre t = 1..T)
-------------------------------
0) Escenario común a toda la sesión, sorteado al crearla (con semilla):
       inflación      π_t = media + desvío · z            (z normal truncada en ±2, π ≥ 0)
       crisis         con probabilidad q por trimestre
       acciones (US$) a_t = μ_a − q·c_a + σ_a · z          (+ c_a si hay crisis)
       dólar          d_t = π_t − q·c_d + σ_tc · z         (+ c_d si hay crisis)
       Las medias μ_a (y la inflación, para el dólar) son promedios que ya incluyen las
       crisis: fuera de ellas se corrigen para compensarlas.
       tasa real      Δρ_t = σ_ρ · z                      (cambio de la tasa real anual de los bonos)

1) Rendimiento nominal en pesos de cada activo en el trimestre:
       acciones   (1 + a_t)(1 + d_t) − 1                  (se compran en dólares)
       bonos      π_t + r_b − D · Δρ_t − q·c_b  (+ c_b si hay crisis)
                  Rinden la inflación más una tasa real r_b (como un bono ajustado por
                  CER) y su precio cae cuando sube la tasa real del mercado, según su
                  duración D en años.
       liquidez   π_e + s                                 (plazo fijo)
                  Tasa pactada al empezar el trimestre con la inflación esperada
                  π_e = media; s < 0: en promedio pierde un poco contra la inflación.

2) Decisión: porcentajes (acciones, bonos, liquidez) que suman 100 %, en pasos.
   Al empezar cada trimestre se rebalancea la cartera a esos porcentajes. Comprar
   o vender acciones o bonos paga una comisión sobre el monto operado; la
   liquidez es el dinero disponible y no paga comisión.

3) Valor de la cartera: V_t = Σ_i (monto_i después de rebalancear) · (1 + r_i,t).
   En moneda constante: V_t / I_t, con I_t el índice de precios (I_0 = 1).

4) Evaluación: rentabilidad real de cada año, TEA real del período, volatilidad
   anualizada, índice de Sharpe (contra la liquidez) y caída máxima, en pesos
   constantes; también el valor en dólares.
"""
import math
import random

from nucleo.inflacion import siguiente_indice, truncada

ACTIVOS = ('acciones', 'bonos', 'liquidez')

# Parámetros que necesita el modelo (todos deben estar en `params`).
PARAMETROS = [
    'capital_inicial',      # $ al empezar
    'inflacion_media',      # inflación trimestral media (también es la esperada para el plazo fijo)
    'inflacion_desvio',     # desvío de la inflación trimestral
    'acciones_media',       # rendimiento trimestral medio de las acciones, en dólares
    'acciones_desvio',      # desvío trimestral de las acciones, en dólares
    'dolar_desvio',         # desvío trimestral de la variación del dólar respecto de la inflación
    'bonos_tasa_real',      # tasa real trimestral de los bonos
    'bonos_duracion',       # duración de los bonos, en años
    'bonos_desvio_tasa',    # desvío trimestral del cambio de la tasa real anual (en puntos: 0.005 = 0,5 pp)
    'liquidez_diferencial', # tasa del plazo fijo = inflación esperada + diferencial (negativo)
    'prob_crisis',          # probabilidad de crisis en cada trimestre
    'crisis_acciones',      # choque de las acciones en dólares en una crisis
    'crisis_dolar',         # salto adicional del dólar en una crisis
    'crisis_bonos',         # choque de los bonos en una crisis
    'comision',             # sobre el monto comprado o vendido de acciones y bonos
    'precision_noticias',   # probabilidad de que el titular anticipe bien a las acciones
]

# Carteras de referencia para comparar (acciones, bonos, liquidez).
REFERENCIAS = {
    'Equilibrada 60/30/10': (0.60, 0.30, 0.10),
    'Todo en liquidez': (0.0, 0.0, 1.0),
    'Todo en acciones': (1.0, 0.0, 0.0),
}


# --- Escenario de la sesión ---------------------------------------------------

def generar_escenario(params, trimestres, semilla=None):
    """
    Escenario de mercado común a toda la sesión: lista de un dict por trimestre con
    inflación, crisis, rendimientos de cada activo (nominales, en pesos), variación
    del dólar, índice de precios y tipo de cambio (ambos = 1 al empezar) y el titular
    de noticias que se publica ANTES de decidir ese trimestre.
    """
    rnd = random.Random(semilla)
    p = params
    indice, dolar = 1.0, 1.0
    escenario = []
    for t in range(1, trimestres + 1):
        inflacion = max(0.0, p['inflacion_media'] + truncada(rnd) * p['inflacion_desvio'])
        crisis = rnd.random() < p['prob_crisis']
        # Las medias incluyen a las crisis: fuera de ellas se corrigen para que el promedio
        # de todos los trimestres sea el del parámetro (el dólar, por ejemplo, se atrasa un
        # poco en tiempos normales y salta en las crisis).
        q = p['prob_crisis']
        acciones_usd = p['acciones_media'] - q * p['crisis_acciones'] + truncada(rnd) * p['acciones_desvio']
        var_dolar = inflacion - q * p['crisis_dolar'] + truncada(rnd) * p['dolar_desvio']
        cambio_tasa = truncada(rnd) * p['bonos_desvio_tasa']
        choque_bonos = -q * p['crisis_bonos']
        if crisis:
            acciones_usd += p['crisis_acciones']
            var_dolar += p['crisis_dolar']
            choque_bonos += p['crisis_bonos']
        acciones_usd = max(acciones_usd, -0.95)
        var_dolar = max(var_dolar, -0.5)

        rendimientos = dict(
            acciones=(1 + acciones_usd) * (1 + var_dolar) - 1,
            bonos=max(-0.95, inflacion + p['bonos_tasa_real'] - p['bonos_duracion'] * cambio_tasa + choque_bonos),
            liquidez=p['inflacion_media'] + p['liquidez_diferencial'],
        )

        # Titular: anticipa si a las acciones les irá mejor o peor que lo normal; acierta
        # con probabilidad `precision_noticias`. Una crisis siempre se anuncia como mala
        # noticia salvo cuando el titular se equivoca.
        buena = acciones_usd >= p['acciones_media'] - q * p['crisis_acciones'] if not crisis else False
        acierta = rnd.random() < p['precision_noticias']
        noticia = ('optimista' if buena else 'pesimista') if acierta else ('pesimista' if buena else 'optimista')

        indice = siguiente_indice(indice, inflacion)
        dolar = dolar * (1 + var_dolar)
        escenario.append(dict(
            trimestre=t,
            inflacion=inflacion,
            crisis=crisis,
            acciones_usd=acciones_usd,
            var_dolar=var_dolar,
            cambio_tasa=cambio_tasa,
            rendimientos=rendimientos,
            noticia=noticia,
            indice=indice,       # al terminar el trimestre
            dolar=dolar,         # al terminar el trimestre
        ))
    return escenario


# --- Decisiones -----------------------------------------------------------------

def validar_porcentajes(pesos, paso=0.05):
    """None si los porcentajes son válidos; si no, el texto del problema."""
    if len(pesos) != 3:
        return 'Tiene que indicar un porcentaje para cada activo.'
    if any(w < -1e-9 or w > 1 + 1e-9 for w in pesos):
        return 'Cada porcentaje tiene que estar entre 0 % y 100 %.'
    if any(abs(w / paso - round(w / paso)) > 1e-6 for w in pesos):
        return f'Los porcentajes van de {round(paso * 100)} % en {round(paso * 100)} %.'
    if abs(sum(pesos) - 1) > 1e-6:
        return f'Los porcentajes suman {sum(pesos) * 100:.0f} % y tienen que sumar 100 %.'
    return None


# --- Un trimestre de una cartera ----------------------------------------------------

def rebalancear(montos, pesos, comision):
    """
    Lleva la cartera a los porcentajes elegidos. Devuelve (montos nuevos, comisión pagada).
    La comisión se paga sobre lo que se compra o vende de acciones y bonos y sale del
    total, así que se resuelve el valor final V de forma que
        V = total − comisión · Σ_{acciones, bonos} |w_i · V − monto_i|.
    """
    total = sum(montos)
    v = total
    for _ in range(100):   # punto fijo: converge enseguida porque la comisión es chica
        operado = sum(abs(pesos[i] * v - montos[i]) for i in (0, 1))
        nuevo = total - comision * operado
        listo = abs(nuevo - v) <= 1e-12 * max(total, 1.0)
        v = nuevo
        if listo:
            break
    operado = sum(abs(pesos[i] * v - montos[i]) for i in (0, 1))
    return [w * v for w in pesos], comision * operado


def simular_trimestre(montos, pesos, datos, comision):
    """
    Un trimestre: rebalanceo al empezar y rendimiento de cada activo.
    `montos`: lo que hay en cada activo al empezar (en pesos de ese momento).
    Devuelve un dict con los montos finales, la comisión y el rendimiento nominal de la cartera.
    """
    invertido, costo = rebalancear(montos, pesos, comision)
    finales = [m * (1 + datos['rendimientos'][a]) for m, a in zip(invertido, ACTIVOS)]
    inicial = sum(montos)
    return dict(
        invertido=invertido,
        montos=finales,
        comision=costo,
        valor_inicial=inicial,
        valor_final=sum(finales),
        rendimiento=sum(finales) / inicial - 1,
    )


def simular_cartera(decisiones, escenario, params):
    """
    Recorre el escenario con las decisiones de un equipo (una tupla de porcentajes por
    trimestre). Al empezar, todo el capital está en liquidez. Devuelve la lista de
    trimestres con el valor nominal, real (pesos del inicio) y en dólares.
    """
    montos = [0.0, 0.0, float(params['capital_inicial'])]
    filas = []
    for pesos, datos in zip(decisiones, escenario):
        r = simular_trimestre(montos, pesos, datos, params['comision'])
        montos = r['montos']
        r.update(
            trimestre=datos['trimestre'],
            pesos=tuple(pesos),
            valor_real=r['valor_final'] / datos['indice'],
            valor_dolares=r['valor_final'] / datos['dolar'],
            rendimiento_real=(1 + r['rendimiento']) / (1 + datos['inflacion']) - 1,
        )
        filas.append(r)
    return filas


# --- Evaluación -------------------------------------------------------------------

def tea(valor_final, valor_inicial, trimestres):
    """Tasa efectiva anual equivalente a pasar de valor_inicial a valor_final en `trimestres`."""
    if trimestres <= 0 or valor_inicial <= 0:
        return 0.0
    return (valor_final / valor_inicial) ** (4 / trimestres) - 1


def caida_maxima(valores, inicial):
    """Mayor caída desde un máximo previo (0.25 = cayó 25 %)."""
    maximo, peor = inicial, 0.0
    for v in valores:
        maximo = max(maximo, v)
        peor = max(peor, 1 - v / maximo)
    return peor


def evaluar(filas, escenario, params):
    """Indicadores de la cartera en moneda constante (y en dólares)."""
    capital = params['capital_inicial']
    n = len(filas)
    reales = [f['rendimiento_real'] for f in filas]
    liquidez_real = [(1 + d['rendimientos']['liquidez']) / (1 + d['inflacion']) - 1 for d in escenario[:n]]
    media = sum(reales) / n if n else 0.0
    desvio = math.sqrt(sum((r - media) ** 2 for r in reales) / (n - 1)) if n > 1 else 0.0
    exceso = media - (sum(liquidez_real) / n if n else 0.0)

    anios = []
    for k in range(0, n, 4):
        tramo = filas[k:k + 4]
        inicio = capital if k == 0 else filas[k - 1]['valor_real']
        anios.append(dict(anio=k // 4 + 1, trimestres=len(tramo),
                          rentabilidad_real=tramo[-1]['valor_real'] / inicio - 1))
    return dict(
        valor_final=filas[-1]['valor_final'] if filas else capital,
        valor_real=filas[-1]['valor_real'] if filas else capital,
        valor_dolares=filas[-1]['valor_dolares'] if filas else capital,
        tea_real=tea(filas[-1]['valor_real'], capital, n) if filas else 0.0,
        tea_dolares=tea(filas[-1]['valor_dolares'], capital, n) if filas else 0.0,
        volatilidad=desvio * 2,                                    # anualizada (√4)
        sharpe=(exceso * 4) / (desvio * 2) if desvio > 0 else 0.0,
        caida_maxima=caida_maxima([f['valor_real'] for f in filas], capital),
        comisiones=sum(f['comision'] for f in filas),
        anios=anios,
    )


def referencias(escenario, params):
    """Evaluación de las carteras de referencia en el mismo escenario."""
    return {nombre: evaluar(simular_cartera([pesos] * len(escenario), escenario, params), escenario, params)
            for nombre, pesos in REFERENCIAS.items()}
