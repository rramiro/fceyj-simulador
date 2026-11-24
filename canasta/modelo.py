"""
Modelo del juego "La canasta de Soledad" (Microeconomía, unidades II y III: comportamiento del consumidor
y demanda).

Funciones puras (no dependen de oTree). Se prueban y calibran con scripts/simular_canasta.py.

El juego
--------
- Cada equipo es un consumidor que reparte su ingreso del mes entre dos bienes, como Soledad y López en el
  TP 1 de la cátedra: X = entradas al cine (enteras) e Y = alimentos (en canastas, divisibles).
- Decide cuántas entradas compra; los alimentos son lo que queda del ingreso: Y = (I − Px·X) / Py.
  Siempre está sobre la recta de presupuesto.
- Las preferencias son de elasticidad de sustitución constante (CES), homogéneas de grado 1:

        U(X, Y) = [a·X^r + (1 − a)·Y^r]^(1/r),   r = (σ − 1) / σ        (σ = 1: Cobb-Douglas X^a·Y^(1−a))

  Hay tres tipos de consumidor (TIPOS), repartidos entre los equipos. Como U es homogénea de grado 1,
  U(elegida) / U(óptima) dice qué fracción del ingreso "real" lograron: elegir mal equivale a perder
  (1 − U/U*)·I de ingreso.
- Ocho meses (RONDAS), con los precios y el ingreso del TP 1 (López: I = 16, Px = 2, Py = 1, escalados):
  base, promoción del cine, suba del cine, baja del ingreso, aguinaldo, suba de los alimentos, suba del cine
  con compensación de Slutsky (el ingreso alcanza justo para la canasta de marzo) y todo junto.
- Puntaje de la decisión: según la distancia (en entradas) a la cantidad óptima entera del tipo.
- Pregunta del mes: TMS en el óptimo o una elasticidad arco (precio, ingreso, cruzada) o el efecto
  sustitución, calculados con las cantidades que eligió el propio equipo.
"""
import math

TIPOS = {
    # a: peso del cine; sigma: elasticidad de sustitución.
    'equilibrado': dict(nombre='Equilibrado', a=0.4, sigma=1.0,
                        descripcion='Le gustan las dos cosas y las combina en cualquier proporción: '
                                    'sus curvas de indiferencia son las "de manual".'),
    'cinefilo': dict(nombre='Cinéfilo', a=0.45, sigma=2.0,
                     descripcion='Cambia fácil cine por comida y comida por cine: sus curvas de indiferencia son '
                                 'casi rectas.'),
    'combo': dict(nombre='Combo', a=0.2, sigma=0.5,
                  descripcion='El cine sin comida (o la comida sin salidas) no le rinde: le gusta consumirlos '
                              'juntos y sus curvas de indiferencia son muy curvas.'),
}
ORDEN_TIPOS = ['equilibrado', 'cinefilo', 'combo']

RONDAS = [
    # mes, título, multiplicadores del ingreso y de los precios base, compensada (Slutsky), anuncio
    dict(mes='Marzo', titulo='Un mes normal', ingreso=1.0, px=1.0, py=1.0,
         anuncio='Arranca el año: ingreso y precios de siempre.'),
    dict(mes='Abril', titulo='Promo en el cine', ingreso=1.0, px=0.5, py=1.0,
         anuncio='El cine lanza una promoción: todas las entradas a mitad de precio durante el mes.'),
    dict(mes='Mayo', titulo='Sube el cine', ingreso=1.0, px=2.0, py=1.0,
         anuncio='Terminó la promo y el cine aumentó: la entrada cuesta el doble que en marzo.'),
    dict(mes='Junio', titulo='Baja el ingreso', ingreso=0.75, px=1.0, py=1.0,
         anuncio='Este mes trabajan menos horas: el ingreso baja un 25 %. Los precios vuelven a los de marzo.'),
    dict(mes='Julio', titulo='Aguinaldo', ingreso=1.5, px=1.0, py=1.0,
         anuncio='¡Cobran el aguinaldo! El ingreso del mes es 50 % más alto, con los precios de marzo.'),
    dict(mes='Agosto', titulo='Suben los alimentos', ingreso=1.0, px=1.0, py=2.0,
         anuncio='Los alimentos duplican su precio; el cine y el ingreso siguen como en marzo.'),
    dict(mes='Septiembre', titulo='Sube el cine, con compensación', ingreso=None, px=2.0, py=1.0, compensada=True,
         anuncio='La entrada vuelve a costar el doble, pero la familia les da una ayuda: el ingreso del mes '
                 'alcanza justo para comprar la misma canasta que eligieron en marzo.'),
    dict(mes='Octubre', titulo='Cambia todo', ingreso=1.25, px=0.5, py=2.0,
         anuncio='Mes movido: suben el ingreso (+25 %) y los alimentos (el doble), y vuelve la promo del cine '
                 '(mitad de precio).'),
]

PARAMETROS = [
    'ingreso_base',         # ingreso del mes en marzo ($)
    'precio_cine',          # Px en marzo ($ por entrada)
    'precio_alimentos',     # Py en marzo ($ por canasta de alimentos)
    'puntos_exacto', 'puntos_a_uno', 'puntos_a_dos',   # puntos de la decisión según la distancia al óptimo
    'tolerancia_pregunta',
    'puntos_pregunta',
]


def tipo_de_equipo(posicion):
    """Tipo de consumidor del equipo n.º `posicion` (1, 2, ...): se reparten en orden."""
    return ORDEN_TIPOS[(posicion - 1) % len(ORDEN_TIPOS)]


# --- Preferencias ---------------------------------------------------------------------------

def utilidad(x, y, tipo):
    t = TIPOS[tipo]
    a, s = t['a'], t['sigma']
    if x < 0 or y < 0:
        return 0.0
    if abs(s - 1) < 1e-12:
        return x ** a * y ** (1 - a)
    r = (s - 1) / s
    if r < 0 and (x == 0 or y == 0):
        return 0.0
    return (a * x ** r + (1 - a) * y ** r) ** (1 / r)


def tms(x, y, tipo):
    """Tasa marginal de sustitución de Y por X: UMgX / UMgY = a/(1−a) · (Y/X)^(1/σ)."""
    t = TIPOS[tipo]
    if x <= 0:
        return math.inf
    return t['a'] / (1 - t['a']) * (y / x) ** (1 / t['sigma'])


def y_indiferencia(x, u, tipo):
    """Y sobre la curva de indiferencia de nivel u para un X dado (None si no hay)."""
    t = TIPOS[tipo]
    a, s = t['a'], t['sigma']
    if x <= 0:
        return None
    if abs(s - 1) < 1e-12:
        return (u / x ** a) ** (1 / (1 - a))
    r = (s - 1) / s
    resto = u ** r - a * x ** r
    if resto <= 0:
        return None
    return (resto / (1 - a)) ** (1 / r)


def demanda_continua(ingreso, px, py, tipo):
    """X óptimo sin restricción de enteros (la fórmula de la demanda CES)."""
    t = TIPOS[tipo]
    a, s = t['a'], t['sigma']
    den = a ** s * px ** (1 - s) + (1 - a) ** s * py ** (1 - s)
    return a ** s * px ** (-s) * ingreso / den


# --- Meses ----------------------------------------------------------------------------------

def datos_ronda(ronda, params, x_marzo=None):
    """Ingreso y precios del mes. En el mes compensado el ingreso depende de la canasta de marzo del equipo
    (x_marzo, con sus alimentos sobre la recta de marzo)."""
    r = RONDAS[ronda - 1]
    p = params
    px = p['precio_cine'] * r['px']
    py = p['precio_alimentos'] * r['py']
    if r.get('compensada'):
        if x_marzo is None:
            x_marzo = 0
        y_marzo = (p['ingreso_base'] - p['precio_cine'] * x_marzo) / p['precio_alimentos']
        ingreso = px * x_marzo + py * y_marzo
    else:
        ingreso = p['ingreso_base'] * r['ingreso']
    return dict(ronda=ronda, mes=r['mes'], titulo=r['titulo'], anuncio=r['anuncio'],
                compensada=bool(r.get('compensada')), ingreso=ingreso, px=px, py=py,
                x_max=int(ingreso // px + 1e-9))


def alimentos(x, d):
    return (d['ingreso'] - d['px'] * x) / d['py']


def optimo(d, tipo):
    """(X, Y, U) óptimos con X entero."""
    mejor = None
    for x in range(0, d['x_max'] + 1):
        y = alimentos(x, d)
        u = utilidad(x, y, tipo)
        if mejor is None or u > mejor[2] + 1e-12:
            mejor = (x, y, u)
    return mejor


def puntos_decision(x, x_opt, params):
    dist = abs(x - x_opt)
    if dist == 0:
        return params['puntos_exacto']
    if dist == 1:
        return params['puntos_a_uno']
    if dist == 2:
        return params['puntos_a_dos']
    return 0


# --- Pregunta del mes -----------------------------------------------------------------------

def elasticidad_arco(q1, q2, v1, v2):
    """Elasticidad arco (punto medio). None si no se puede calcular."""
    if q1 + q2 == 0 or v1 + v2 == 0 or v1 == v2:
        return None
    return ((q2 - q1) / ((q1 + q2) / 2)) / ((v2 - v1) / ((v1 + v2) / 2))


def pregunta_de_la_ronda(ronda, params, x_marzo, x_actual):
    """(texto, valor correcto o None si no se puede calcular, unidad, valor_absoluto).
    Se responde con las cantidades del propio equipo: la de marzo y la que eligen en el mes.
    valor_absoluto=True: se acepta la elasticidad precio con o sin el signo."""
    d = datos_ronda(ronda, params, x_marzo)
    m = datos_ronda(1, params)
    if ronda in (1, 8):
        return ('¿Cuánto vale la tasa marginal de sustitución de alimentos por entradas (TMS = UMgX / UMgY) en la '
                'canasta óptima del mes?', d['px'] / d['py'], 'canastas por entrada', False)
    if ronda in (2, 3):
        return (f'Con las entradas que compraron en marzo y las que compran ahora, calculen la elasticidad arco '
                f'precio de su demanda de cine (punto medio).',
                elasticidad_arco(x_marzo, x_actual, m['px'], d['px']), '(número)', True)
    if ronda in (4, 5):
        return ('Con las entradas que compraron en marzo y las que compran ahora, calculen la elasticidad arco '
                'ingreso de su demanda de cine (punto medio).',
                elasticidad_arco(x_marzo, x_actual, m['ingreso'], d['ingreso']), '(número)', False)
    if ronda == 6:
        return ('Con las entradas que compraron en marzo y las que compran ahora, calculen la elasticidad arco '
                'cruzada de su demanda de cine respecto del precio de los alimentos (punto medio).',
                elasticidad_arco(x_marzo, x_actual, m['py'], d['py']), '(número)', False)
    if ronda == 7:
        return ('Con el ingreso compensado, ¿cuál es su efecto sustitución en entradas (entradas de este mes menos '
                'entradas de marzo)?', float(x_actual - x_marzo), 'entradas', False)
    raise ValueError(ronda)


def acierta(respuesta, correcto, params, valor_absoluto=False):
    """Si el valor correcto no se puede calcular (por ejemplo, cero entradas en los dos meses), la pregunta
    se anula y cuenta como acertada."""
    if correcto is None:
        return True
    if respuesta is None:
        return False
    if valor_absoluto:
        respuesta, correcto = abs(respuesta), abs(correcto)
    tol = params['tolerancia_pregunta'] * abs(correcto)
    if abs(correcto) < 1e-9:
        tol = 0.05   # correcto = 0: se admite un margen fijo
    return abs(respuesta - correcto) <= tol + 1e-9


# --- Mes jugado -----------------------------------------------------------------------------

def jugar_ronda(ronda, x, respuesta, tipo, params, x_marzo):
    """Resultados del mes para el equipo que eligió x entradas."""
    d = datos_ronda(ronda, params, x_marzo if ronda > 1 else None)
    x = max(0, min(int(x), d['x_max']))
    y = alimentos(x, d)
    u = utilidad(x, y, tipo)
    x_opt, y_opt, u_opt = optimo(d, tipo)
    xm = x if ronda == 1 else x_marzo
    texto, correcto, unidad, absoluto = pregunta_de_la_ronda(ronda, params, xm, x)
    acierto = acierta(respuesta, correcto, params, absoluto)
    return dict(
        ronda=ronda, mes=d['mes'], titulo=d['titulo'], tipo=tipo,
        ingreso=d['ingreso'], px=d['px'], py=d['py'], x_max=d['x_max'],
        x=x, y=y, u=u, gasto_cine=d['px'] * x,
        x_opt=x_opt, y_opt=y_opt, u_opt=u_opt, x_continuo=demanda_continua(d['ingreso'], d['px'], d['py'], tipo),
        relativa=u / u_opt if u_opt > 0 else 1.0,
        ingreso_perdido=(1 - (u / u_opt if u_opt > 0 else 1.0)) * d['ingreso'],
        distancia=abs(x - x_opt), puntos=puntos_decision(x, x_opt, params),
        tms_elegida=tms(x, y, tipo) if x > 0 and y > 0 else None, precio_relativo=d['px'] / d['py'],
        pregunta=dict(texto=texto, correcto=correcto, unidad=unidad, absoluto=absoluto,
                      respuesta=respuesta, acierto=acierto,
                      puntos=params['puntos_pregunta'] if acierto else 0),
    )


def puntaje(rondas, params):
    """Puntaje de 0 a 100: decisiones + preguntas sobre el máximo posible en los meses jugados."""
    if not rondas:
        return 0.0
    hecho = sum(r['puntos'] + r['pregunta']['puntos'] for r in rondas)
    maximo = len(rondas) * (params['puntos_exacto'] + params['puntos_pregunta'])
    return 100 * hecho / maximo


def niveles_curvas(u_opt):
    """Niveles de utilidad de las curvas de indiferencia que se dibujan en la decisión (ninguna es la tangente:
    la canasta óptima la tienen que encontrar)."""
    return [u_opt * k for k in (0.6, 0.75, 0.9, 1.06, 1.2)]
