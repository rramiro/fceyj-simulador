"""
Simulación y calibración del modelo de mercado, sin pasar por oTree.

Uso (desde la raíz del proyecto, con el venv activado):
    python scripts/simular_mercado.py
    python scripts/simular_mercado.py beta_precio=3 elasticidad=1.2   # probar otros valores

Toma los parámetros de la primera configuración de SESSION_CONFIGS en settings.py;
los argumentos clave=valor los reemplazan solo para esta corrida.
"""
import importlib.util
import random
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def cargar_modulo(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Se cargan por ruta para no importar oTree (comercializacion/__init__.py lo usa).
mercado = cargar_modulo('mercado', RAIZ / 'comercializacion' / 'mercado.py')
settings = cargar_modulo('settings', RAIZ / 'settings.py')

N_EMPRESAS = 4


def leer_parametros(argv):
    cfg = dict(settings.SESSION_CONFIGS[0])
    for arg in argv:
        k, v = arg.split('=', 1)
        if k not in cfg:
            sys.exit(f'Parámetro desconocido: {k}')
        cfg[k] = float(v)
    return cfg


def fmt(x, dec=0):
    s = f'{abs(x):,.{dec}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('-' if x < 0 else '') + s


# --- Utilidades de cálculo ---------------------------------------------------

def resultado_de(i, decisiones, cfg):
    return mercado.simular_ronda(decisiones, cfg)['empresas'][i]


def rivales_iguales(precio, publicidad, n=N_EMPRESAS):
    return [dict(precio=precio, publicidad=publicidad) for _ in range(n)]


def mejor_respuesta(p_rival, a_rival, cfg, p0, a0):
    """
    Mejor (precio, publicidad) de la empresa 0 si las otras eligen (p_rival, a_rival).
    Búsqueda en grilla alternando precio y publicidad, refinando el paso.
    """
    pmin, pmax, amax = cfg['precio_min'], cfg['precio_max'], cfg['publicidad_max']

    def ganancia(p, a):
        dec = rivales_iguales(p_rival, a_rival)
        dec[0] = dict(precio=p, publicidad=a)
        return resultado_de(0, dec, cfg)['resultado']

    p, a = p0, a0
    paso_p, paso_a = (pmax - pmin) / 50, amax / 50
    for _ in range(6):
        for _ in range(3):
            p = max((min(max(p + k * paso_p, pmin), pmax) for k in range(-25, 26)),
                    key=lambda x: ganancia(x, a))
            a = max((min(max(a + k * paso_a, 0), amax) for k in range(-25, 26)),
                    key=lambda x: ganancia(p, x))
        paso_p /= 5
        paso_a /= 5
    return p, a


def equilibrio_simetrico(cfg):
    """Iteración de mejores respuestas hasta que la empresa no quiera desviarse."""
    p, a = cfg['precio_referencia'], cfg['publicidad_max'] / 4
    for _ in range(40):
        p_nuevo, a_nuevo = mejor_respuesta(p, a, cfg, p, a)
        # amortiguamos para que converja
        p_sig, a_sig = (p + p_nuevo) / 2, (a + a_nuevo) / 2
        if abs(p_sig - p) < 0.5 and abs(a_sig - a) < 100:
            return p_sig, a_sig
        p, a = p_sig, a_sig
    print('  (aviso: el equilibrio no convergió del todo)')
    return p, a


# --- Secciones del informe ---------------------------------------------------

def verificaciones(cfg):
    print('1) Verificaciones del modelo')
    pref = cfg['precio_referencia']

    r = mercado.simular_ronda(rivales_iguales(pref, 1_000_000), cfg)
    partes = [e['participacion'] for e in r['empresas']]
    assert abs(sum(partes) - 1) < 1e-12, 'las participaciones no suman 1'
    assert all(abs(s - 1 / N_EMPRESAS) < 1e-12 for s in partes), 'decisiones iguales => partes iguales'
    assert abs(r['mercado']['demanda_total'] - cfg['demanda_base']) < 1e-6, 'D(p_ref) = D0'

    dec = rivales_iguales(pref, 1_000_000)
    dec[0]['precio'] = pref * 1.1
    r = mercado.simular_ronda(dec, cfg)
    assert r['empresas'][0]['participacion'] < 0.25, 'subir el precio baja la participación'
    assert r['mercado']['demanda_total'] < cfg['demanda_base'], 'subir precios achica el mercado'

    dec = rivales_iguales(pref, 1_000_000)
    dec[0]['publicidad'] = 2_000_000
    r = mercado.simular_ronda(dec, cfg)
    assert r['empresas'][0]['participacion'] > 0.25, 'más publicidad sube la participación'
    print('   OK: participaciones suman 1, simetría, D(p_ref)=D0, efectos de precio y publicidad.\n')


def informe_equilibrio(cfg):
    print('2) Equilibrio simétrico (todas las empresas juegan su mejor respuesta)')
    p, a = equilibrio_simetrico(cfg)
    r = resultado_de(0, rivales_iguales(p, a), cfg)
    D = mercado.demanda_total(p, cfg)
    margen = (p - cfg['costo_variable']) / p
    print(f'   Precio:            $ {fmt(p, 0)}  (margen sobre precio {margen:.0%})')
    print(f'   Publicidad:        $ {fmt(a)} por trimestre')
    print(f'   Demanda total:     {fmt(D)} u.   Unidades por empresa: {fmt(r["unidades"])}')
    print(f'   Ventas:            $ {fmt(r["ventas"])}')
    print(f'   Resultado:         $ {fmt(r["resultado"])} por trimestre')

    # Referencia: si se pusieran de acuerdo (sin publicidad, precio que maximiza el total)
    mejor = max(
        ((pp, resultado_de(0, rivales_iguales(pp, 0), cfg)['resultado'])
         for pp in range(int(cfg['precio_min']), int(cfg['precio_max']) + 1, 10)),
        key=lambda t: t[1])
    print(f'   [Colusión: precio $ {fmt(mejor[0])}, publicidad $ 0 -> resultado $ {fmt(mejor[1])} c/u]\n')
    return p, a, r['resultado']


def informe_extremos(cfg, p_eq, a_eq, res_eq):
    print('3) Una empresa se desvía con una estrategia extrema (las otras 3 en equilibrio)')
    casos = [
        ('Equilibrio (referencia)', p_eq, a_eq),
        ('Precio mínimo', cfg['precio_min'], a_eq),
        ('Precio máximo', cfg['precio_max'], a_eq),
        ('Precio -20 %', p_eq * 0.8, a_eq),
        ('Precio +20 %', p_eq * 1.2, a_eq),
        ('Sin publicidad', p_eq, 0),
        ('Publicidad máxima', p_eq, cfg['publicidad_max']),
        ('Barato y sin publicidad', p_eq * 0.8, 0),
        ('Premium (caro + publicidad máx.)', p_eq * 1.3, cfg['publicidad_max']),
    ]
    print(f'   {"Estrategia":34} {"Precio":>9} {"Publicidad":>12} {"Partic.":>8} {"Resultado":>14} {"vs eq.":>8}')
    for nombre, p, a in casos:
        dec = rivales_iguales(p_eq, a_eq)
        dec[0] = dict(precio=p, publicidad=a)
        r = resultado_de(0, dec, cfg)
        dif = (r['resultado'] - res_eq) / abs(res_eq) if res_eq else 0
        print(f'   {nombre:34} {fmt(p):>9} {fmt(a):>12} {r["participacion"]:>8.1%} '
              f'{fmt(r["resultado"]):>14} {dif:>+8.0%}')
    print()


def informe_aleatorio(cfg, rondas=2000, semilla=1):
    print(f'4) {rondas} mercados con decisiones aleatorias uniformes')
    rnd = random.Random(semilla)
    resultados, partes = [], []
    for _ in range(rondas):
        dec = [dict(precio=rnd.uniform(cfg['precio_min'], cfg['precio_max']),
                    publicidad=rnd.uniform(0, cfg['publicidad_max'])) for _ in range(N_EMPRESAS)]
        for e in mercado.simular_ronda(dec, cfg)['empresas']:
            resultados.append(e['resultado'])
            partes.append(e['participacion'])
    resultados.sort()
    q = statistics.quantiles(resultados, n=10)
    print(f'   Resultado por empresa: mediana $ {fmt(statistics.median(resultados))}, '
          f'P10 $ {fmt(q[0])}, P90 $ {fmt(q[-1])}')
    print(f'   Empresas con pérdida: {sum(r < 0 for r in resultados) / len(resultados):.0%}')
    print(f'   Participación: mín {min(partes):.1%}, máx {max(partes):.1%}\n')


def main():
    cfg = leer_parametros(sys.argv[1:])
    print('Parámetros:', {k: cfg[k] for k in mercado.PARAMETROS}, '\n')
    verificaciones(cfg)
    p, a, res = informe_equilibrio(cfg)
    informe_extremos(cfg, p, a, res)
    informe_aleatorio(cfg)


if __name__ == '__main__':
    main()
