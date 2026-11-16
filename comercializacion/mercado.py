"""
Modelo de mercado del simulador de comercialización.

Este módulo NO depende de oTree: son funciones puras que reciben las
decisiones de las empresas y los parámetros, y devuelven los resultados.
Así se pueden probar y calibrar con scripts (ver scripts/simular_mercado.py)
sin pasar por la interfaz.

Modelo (Versión 1)
------------------
1) Precio medio del mercado (promedio simple de los precios):
       p_medio = (1/n) * Σ p_i

2) Demanda total del mercado, con elasticidad constante al precio medio:
       D = D0 * (p_medio / p_ref) ^ (-ε)
   Si todas cobran p_ref, el mercado demanda D0 unidades.

3) Atractivo de cada empresa:
       a_i = -βp * (p_i / p_medio - 1) + βa * ln(1 + A_i / escala_A)
   - Cobrar más caro que el promedio resta atractivo (βp).
   - La publicidad suma con rendimientos decrecientes (logaritmo).
     'escala_A' es la inversión a partir de la cual el efecto se nota.

4) Participación (modelo logit):
       s_i = exp(a_i) / Σ_j exp(a_j)

5) Por empresa:
       unidades  = s_i * D
       ventas    = unidades * p_i
       resultado = ventas - unidades * c - A_i - costo_fijo
"""

import math

# Parámetros que necesita el modelo (todos deben estar en `params`).
PARAMETROS = [
    'demanda_base',        # D0: unidades por trimestre si todas cobran p_ref
    'precio_referencia',   # p_ref: $ por unidad
    'elasticidad',         # ε: elasticidad de la demanda total al precio medio
    'beta_precio',         # βp: sensibilidad de la participación al precio relativo
    'beta_publicidad',     # βa: sensibilidad de la participación a la publicidad
    'escala_publicidad',   # escala_A: $ (normaliza la publicidad dentro del log)
    'costo_variable',      # c: $ por unidad
    'costo_fijo',          # $ por trimestre y por empresa
]


def precio_medio(precios):
    return sum(precios) / len(precios)


def demanda_total(p_medio, params):
    return params['demanda_base'] * (p_medio / params['precio_referencia']) ** (-params['elasticidad'])


def atractivo(precio, publicidad, p_medio, params):
    efecto_precio = -params['beta_precio'] * (precio / p_medio - 1)
    efecto_publicidad = params['beta_publicidad'] * math.log(1 + publicidad / params['escala_publicidad'])
    return efecto_precio + efecto_publicidad


def participaciones(atractivos):
    """Logit. Se resta el máximo para evitar desbordes numéricos (no cambia el resultado)."""
    m = max(atractivos)
    exps = [math.exp(a - m) for a in atractivos]
    total = sum(exps)
    return [e / total for e in exps]


def simular_ronda(decisiones, params):
    """
    Calcula el resultado de una ronda para todas las empresas de un mercado.

    decisiones: lista de dicts con 'precio' y 'publicidad' (uno por empresa).
    params: dict con los parámetros de PARAMETROS.

    Devuelve un dict con:
      'mercado': {'precio_medio', 'demanda_total'}
      'empresas': lista de dicts (mismo orden que `decisiones`) con
                  participacion, unidades, ventas, costo_variable,
                  costo_publicidad, costo_fijo, resultado.
    """
    faltan = [k for k in PARAMETROS if k not in params]
    if faltan:
        raise KeyError(f'Faltan parámetros del modelo: {faltan}')

    precios = [d['precio'] for d in decisiones]
    pm = precio_medio(precios)
    D = demanda_total(pm, params)
    atractivos = [atractivo(d['precio'], d['publicidad'], pm, params) for d in decisiones]
    partes = participaciones(atractivos)

    empresas = []
    for d, s in zip(decisiones, partes):
        unidades = s * D
        ventas = unidades * d['precio']
        costo_variable = unidades * params['costo_variable']
        costo_publicidad = d['publicidad']
        costo_fijo = params['costo_fijo']
        empresas.append(dict(
            participacion=s,
            unidades=unidades,
            ventas=ventas,
            costo_variable=costo_variable,
            costo_publicidad=costo_publicidad,
            costo_fijo=costo_fijo,
            resultado=ventas - costo_variable - costo_publicidad - costo_fijo,
        ))

    return dict(
        mercado=dict(precio_medio=pm, demanda_total=D),
        empresas=empresas,
    )
