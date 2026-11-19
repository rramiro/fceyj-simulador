"""
Inflación y moneda constante, comunes a todos los juegos.

I_t es el índice de precios del trimestre (I = 1 en el primero). Los montos de
los parámetros se expresan en pesos del primer trimestre y se multiplican por
I_t; para comparar montos de distintos trimestres se reexpresan a una misma
moneda (moneda constante).
"""
import random


def siguiente_indice(indice_anterior, inflacion):
    return indice_anterior * (1 + inflacion)


def reexpresar(monto, indice_origen, indice_destino):
    """Lleva un monto en pesos de un trimestre a pesos de otro (moneda constante)."""
    return monto * indice_destino / indice_origen


def acumular_constante(acumulado_anterior, indice_anterior, resultado, indice):
    """Resultado acumulado en pesos del trimestre actual."""
    return reexpresar(acumulado_anterior, indice_anterior, indice) + resultado


def truncada(rnd=random):
    """Normal estándar truncada en ±2 desvíos."""
    return max(-2.0, min(2.0, rnd.gauss(0, 1)))


def senda_inflacion(media, desvio, trimestres, rnd=random):
    """
    Inflación e índice de cada trimestre de la sesión (listas de largo `trimestres`).
    El primer trimestre no tiene inflación (índice 1); los demás sortean
    media + desvío * normal truncada, sin bajar de cero.
    """
    inflaciones, indices = [0.0], [1.0]
    for _ in range(trimestres - 1):
        pi = max(0.0, media + truncada(rnd) * desvio)
        inflaciones.append(pi)
        indices.append(siguiente_indice(indices[-1], pi))
    return inflaciones, indices
