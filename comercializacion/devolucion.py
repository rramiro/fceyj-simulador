"""
Devolución automática del desempeño de cada empresa.

Funciones puras (no dependen de oTree): reciben el historial de la empresa y
datos del mercado, y devuelven observaciones en texto para el docente y para
el equipo. Los umbrales están juntos al principio para poder ajustarlos.

Cada observación es un dict:
    {'tipo': 'fortaleza' | 'alerta' | 'sugerencia', 'tema': str, 'texto': str}
"""

from nucleo.formato import numero, pesos, porcentaje

# --- Umbrales -----------------------------------------------------------------
PRECIO_ALTO = 1.10            # precio medio relativo al mercado considerado "caro"
PRECIO_BAJO = 0.90            # ... considerado "barato"
MARGEN_BAJO = 0.40            # margen bruto sobre ventas considerado bajo
FALTANTE_ALTO = 0.05          # demanda no atendida / demanda propia
STOCK_ALTO = 0.25             # stock final medio / unidades vendidas
PUBLICIDAD_ALTA = 2.0         # publicidad propia / promedio de los rivales
PUBLICIDAD_BAJA = 0.5
REZAGO_INFLACION = 0.01       # el precio subió al menos 1 punto menos que la inflación


def _pesos(x):
    return pesos(x, 0)


def _numero(x):
    return numero(x, 0)


def _pct(x):
    return porcentaje(x, 0)


def _obs(tipo, tema, texto):
    return dict(tipo=tipo, tema=tema, texto=texto)


def diagnosticar(rondas, puesto, n_empresas, terminado):
    """
    rondas: lista (una por trimestre jugado, en orden) de dicts con:
        precio, precio_medio, publicidad, publicidad_rivales (promedio de los demás),
        produccion, demanda, unidades, faltante, stock_final, participacion,
        ventas, costo_ventas, costo_almacenamiento, costo_financiero,
        costo_investigacion, baja_stock, resultado, inflacion, estudios (int).
    puesto: posición actual en el mercado por resultado acumulado (1 = primero).
    n_empresas: empresas del mercado.
    terminado: True si ya se jugó el último trimestre.
    """
    if not rondas:
        return []
    obs = []
    n = len(rondas)

    # 1) Posición
    verbo = 'Terminó' if terminado else 'Va'
    if puesto == 1:
        obs.append(_obs('fortaleza', 'Resultado', f'{verbo} en el primer puesto de su mercado.'))
    elif puesto == n_empresas:
        obs.append(_obs('alerta', 'Resultado', f'{verbo} en el último puesto de su mercado ({puesto} de {n_empresas}).'))
    else:
        obs.append(_obs('sugerencia', 'Resultado', f'{verbo} en el puesto {puesto} de {n_empresas}.'))

    # 2) Precio frente al mercado
    relativo = sum(r['precio'] / r['precio_medio'] for r in rondas) / n
    participacion = sum(r['participacion'] for r in rondas) / n
    ventas = sum(r['ventas'] for r in rondas)
    margen = (ventas - sum(r['costo_ventas'] for r in rondas)) / ventas if ventas else 0
    justa = 1 / n_empresas
    if relativo > PRECIO_ALTO:
        if participacion < 0.85 * justa:
            obs.append(_obs('alerta', 'Precio',
                            f'Cobró en promedio {_pct(relativo - 1)} más que el mercado y su participación '
                            f'quedó en {_pct(participacion)} (la parte "justa" sería {_pct(justa)}). '
                            'El precio alto le costó clientes.'))
        else:
            obs.append(_obs('fortaleza', 'Precio',
                            f'Cobró {_pct(relativo - 1)} más que el mercado y aun así sostuvo una participación '
                            f'de {_pct(participacion)}: logró diferenciarse.'))
    elif relativo < PRECIO_BAJO:
        if margen < MARGEN_BAJO:
            obs.append(_obs('alerta', 'Precio',
                            f'Cobró en promedio {_pct(1 - relativo)} menos que el mercado y su margen bruto fue '
                            f'de {_pct(margen)}. Ganó clientes, pero cada venta dejó poco.'))
        else:
            obs.append(_obs('fortaleza', 'Precio',
                            f'Con precios {_pct(1 - relativo)} por debajo del mercado mantuvo un margen bruto '
                            f'de {_pct(margen)}.'))
    else:
        obs.append(_obs('fortaleza', 'Precio',
                        f'Se mantuvo cerca del precio de mercado (en promedio {_pct(relativo)} del precio medio), '
                        f'con un margen bruto de {_pct(margen)}.'))

    # 3) Precio e inflación (desde el segundo trimestre)
    rezagos = [i + 1 for i in range(1, n)
               if rondas[i]['precio'] / rondas[i - 1]['precio'] < 1 + rondas[i]['inflacion'] - REZAGO_INFLACION]
    if n > 1 and len(rezagos) >= max(1, (n - 1) / 2):
        trimestres = ', '.join(f'T{t}' for t in rezagos)
        obs.append(_obs('sugerencia', 'Inflación',
                        f'En {trimestres} su precio subió menos que la inflación: en términos reales lo bajaron. '
                        'Conviene decidir el precio pensando en pesos constantes.'))

    # 4) Producción y stock
    demanda = sum(r['demanda'] for r in rondas)
    faltante = sum(r['faltante'] for r in rondas)
    unidades = sum(r['unidades'] for r in rondas)
    stock_medio = sum(r['stock_final'] for r in rondas) / n
    costo_stock = sum(r['costo_almacenamiento'] + r['costo_financiero'] for r in rondas)
    baja = sum(r['baja_stock'] for r in rondas)
    estudios = sum(r['estudios'] for r in rondas)
    problemas_stock = False
    if demanda and faltante / demanda > FALTANTE_ALTO:
        problemas_stock = True
        obs.append(_obs('alerta', 'Producción',
                        f'No pudieron atender {_numero(faltante)} unidades ({_pct(faltante / demanda)} de su demanda) '
                        'por falta de stock: esos clientes compraron a la competencia.'))
    if unidades and stock_medio / (unidades / n) > STOCK_ALTO:
        problemas_stock = True
        obs.append(_obs('alerta', 'Producción',
                        f'Cerraron los trimestres con {_numero(stock_medio)} unidades de stock en promedio, '
                        f'que costaron {_pesos(costo_stock)} en almacenamiento y costo financiero.'))
    if baja > 0:
        problemas_stock = True
        ultima = rondas[-1]['stock_final']
        obs.append(_obs('alerta', 'Producción',
                        f'Al terminar el juego sobraron {_numero(ultima)} unidades, una pérdida de {_pesos(baja)}.'))
    if not problemas_stock:
        obs.append(_obs('fortaleza', 'Producción',
                        'Ajustaron bien la producción a la demanda: casi sin faltantes ni stock acumulado.'))
    elif estudios == 0:
        obs.append(_obs('sugerencia', 'Producción',
                        'No compraron estudios de mercado: el pronóstico de demanda ayuda a decidir cuánto producir, '
                        'sobre todo con la estacionalidad.'))

    # 5) Publicidad
    propia = sum(r['publicidad'] for r in rondas)
    rivales = sum(r['publicidad_rivales'] for r in rondas)
    if propia == 0:
        obs.append(_obs('alerta', 'Publicidad',
                        'No invirtieron en publicidad: su atractivo dependió solo del precio.'))
    elif rivales and propia / rivales > PUBLICIDAD_ALTA:
        obs.append(_obs('sugerencia', 'Publicidad',
                        f'Invirtieron {f"{propia / rivales:.1f}".replace(".", ",")} veces lo que invirtió '
                        'en promedio cada rival. '
                        'La publicidad tiene rendimientos decrecientes: los últimos pesos rinden poco.'))
    elif rivales and propia / rivales < PUBLICIDAD_BAJA:
        obs.append(_obs('sugerencia', 'Publicidad',
                        'Invirtieron menos de la mitad que sus rivales en publicidad y eso les restó atractivo.'))
    else:
        obs.append(_obs('fortaleza', 'Publicidad',
                        'Su inversión en publicidad estuvo en línea con la de sus rivales.'))
    cortes = [i + 1 for i in range(1, n) if rondas[i - 1]['publicidad'] > 0 and rondas[i]['publicidad'] == 0]
    if cortes:
        obs.append(_obs('sugerencia', 'Publicidad',
                        f'Cortaron la publicidad en {", ".join(f"T{t}" for t in cortes)}. Como su efecto se acumula, '
                        'sostenerla suele rendir más que invertir de a saltos.'))

    # 6) Estudios de mercado
    gasto = sum(r['costo_investigacion'] for r in rondas)
    if estudios:
        obs.append(_obs('fortaleza' if not problemas_stock else 'sugerencia', 'Información',
                        f'Compraron {estudios} estudio{"s" if estudios != 1 else ""} de mercado por {_pesos(gasto)}.'
                        + ('' if not problemas_stock else ' Revisen si usaron esa información al decidir la producción.')))
    return obs
