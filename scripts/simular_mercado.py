"""
Simulación y calibración del modelo de mercado, sin pasar por oTree.

Uso (desde la raíz del proyecto, con el venv activado):
    python scripts/simular_mercado.py
    python scripts/simular_mercado.py beta_precio=3 retencion_publicidad=0.7   # probar otros valores

Toma los parámetros de la primera configuración de SESSION_CONFIGS en settings.py;
los argumentos clave=valor los reemplazan solo para esta corrida.
"""
import importlib.util
import random
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))   # para importar nucleo/ (lo usa el modelo)


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
        cfg[k] = v if isinstance(cfg[k], str) else float(v)
    # Cantidad de empresas por mercado (se puede probar otra: empresas_por_mercado=6) y la
    # demanda del mercado, que crece con ella (igual que en la app).
    global N_EMPRESAS
    N_EMPRESAS = int(cfg.get('empresas_por_mercado', 4))
    cfg['demanda_base'] = mercado.demanda_del_mercado(cfg['demanda_por_empresa'], N_EMPRESAS)
    return cfg


def fmt(x, dec=0):
    s = f'{abs(x):,.{dec}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('-' if x < 0 else '') + s


# --- Estado estacionario -----------------------------------------------------
# Para calibrar, cada empresa sostiene la misma publicidad A todos los
# trimestres: su stock publicitario converge a A / (1 - λ). Produce justo lo
# que vende (sin stock), en un trimestre promedio (sin estacionalidad ni shock).

def estacionario(cfg, decisiones):
    lam = cfg['retencion_publicidad']
    estados = [dict(stock_inicial=0, stock_publicidad_anterior=lam * d['publicidad'] / (1 - lam))
               for d in decisiones]
    # Primero sin límite de stock para saber la demanda; después producen exactamente eso.
    dec = [dict(d, produccion=1e12) for d in decisiones]
    r = mercado.simular_ronda(dec, estados, cfg)
    dec = [dict(d, produccion=e['demanda']) for d, e in zip(decisiones, r['empresas'])]
    return mercado.simular_ronda(dec, estados, cfg)


def resultado_de(i, decisiones, cfg):
    return estacionario(cfg, decisiones)['empresas'][i]


def iguales(precio, publicidad, n=None):
    return [dict(precio=precio, publicidad=publicidad) for _ in range(n or N_EMPRESAS)]


def mejor_respuesta(p_rival, a_rival, cfg, p0, a0):
    """Mejor (precio, publicidad) de la empresa 0 si las demás eligen (p_rival, a_rival)."""
    pmin, pmax, amax = cfg['precio_min'], cfg['precio_max'], cfg['publicidad_max']

    def ganancia(p, a):
        dec = iguales(p_rival, a_rival)
        dec[0] = dict(precio=p, publicidad=a)
        return resultado_de(0, dec, cfg)['resultado']

    p, a = p0, a0
    paso_p, paso_a = (pmax - pmin) / 50, amax / 50
    for _ in range(5):
        for _ in range(3):
            p = max((min(max(p + k * paso_p, pmin), pmax) for k in range(-25, 26)),
                    key=lambda x: ganancia(x, a))
            a = max((min(max(a + k * paso_a, 0), amax) for k in range(-25, 26)),
                    key=lambda x: ganancia(p, x))
        paso_p /= 5
        paso_a /= 5
    return p, a


def equilibrio_simetrico(cfg):
    p, a = cfg['precio_referencia'], cfg['publicidad_max'] / 4
    for _ in range(40):
        p_nuevo, a_nuevo = mejor_respuesta(p, a, cfg, p, a)
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
    sin_estado = [dict(stock_inicial=0, stock_publicidad_anterior=0) for _ in range(N_EMPRESAS)]

    def ronda(dec, estados=sin_estado, **kw):
        return mercado.simular_ronda(dec, estados, cfg, **kw)

    dec = [dict(precio=pref, publicidad=1_000_000, produccion=1e9) for _ in range(N_EMPRESAS)]
    r = ronda(dec)
    partes = [e['preferencia'] for e in r['empresas']]
    assert abs(sum(partes) - 1) < 1e-12, 'las participaciones no suman 1'
    assert all(abs(s - 1 / N_EMPRESAS) < 1e-12 for s in partes), 'decisiones iguales => partes iguales'
    assert abs(r['mercado']['demanda_total'] - cfg['demanda_base']) < 1e-6, 'D(p_ref) = D0'

    dec2 = [dict(d) for d in dec]
    dec2[0]['precio'] = pref * 1.1
    assert ronda(dec2)['empresas'][0]['preferencia'] < 1 / N_EMPRESAS, 'subir el precio baja la participación'

    dec2 = [dict(d) for d in dec]
    dec2[0]['publicidad'] = 2_000_000
    assert ronda(dec2)['empresas'][0]['preferencia'] > 1 / N_EMPRESAS, 'más publicidad sube la participación'

    # Publicidad acumulada: el stock anterior suma atractivo aunque hoy no invierta.
    est = [dict(e) for e in sin_estado]
    est[0]['stock_publicidad_anterior'] = 4_000_000
    dec2 = [dict(d, publicidad=0) for d in dec]
    r = ronda(dec2, est)
    assert abs(r['empresas'][0]['stock_publicidad'] - cfg['retencion_publicidad'] * 4_000_000) < 1e-6
    assert r['empresas'][0]['preferencia'] > 1 / N_EMPRESAS, 'el stock publicitario anterior suma atractivo'

    # Faltantes: la empresa 0 sin stock -> su demanda pasa a las demás.
    D = r_base = ronda(dec)['mercado']['demanda_total']
    dec2 = [dict(d) for d in dec]
    dec2[0]['produccion'] = 0
    r = ronda(dec2)
    e = r['empresas']
    assert e[0]['unidades'] == 0 and abs(e[0]['faltante'] - D / N_EMPRESAS) < 1e-6
    vendidas = sum(x['unidades'] for x in e)
    esperado = D if cfg['traspaso_faltantes'] == 1 else D * (1 - (1 / N_EMPRESAS) * (1 - cfg['traspaso_faltantes']))
    assert abs(vendidas - esperado) < 1e-6, 'la demanda no atendida pasa a la competencia'

    # Nadie tiene stock suficiente -> se vende todo lo disponible.
    dec2 = [dict(d, produccion=1000) for d in dec]
    r = ronda(dec2)
    assert all(abs(x['unidades'] - 1000) < 1e-6 for x in r['empresas'])

    # Stock: lo no vendido queda en stock, paga almacenamiento y en la última ronda se da de baja.
    dec2 = [dict(d, produccion=D / N_EMPRESAS + 500) for d in dec]
    r = ronda(dec2, ultima_ronda=True)
    x = r['empresas'][0]
    assert abs(x['stock_final'] - 500) < 1e-6
    assert abs(x['costo_almacenamiento'] - 500 * cfg['costo_almacenamiento']) < 1e-6
    assert abs(x['baja_stock'] - 500 * cfg['costo_variable']) < 1e-6

    # Estacionalidad
    f = mercado.factores_estacionales(cfg['estacionalidad'])
    assert len(f) == 4 and abs(sum(f) / 4 - 1) < 1e-9, 'los factores estacionales deben promediar 1'
    assert [mercado.trimestre_del_anio(r, 3) for r in range(1, 7)] == [3, 4, 1, 2, 3, 4]

    # Inflación: si todos los montos nominales suben con el índice, las unidades no
    # cambian y los resultados se multiplican por el índice (neutralidad).
    I = 1.37
    est = [dict(stock_inicial=300, valor_stock_inicial=300 * cfg['costo_variable'],
                stock_publicidad_anterior=1_000_000) for _ in range(N_EMPRESAS)]
    dec = [dict(precio=pref * (1 + 0.05 * i), publicidad=800_000 * (i + 1), produccion=9000 + 500 * i,
                costo_investigacion=400_000) for i in range(N_EMPRESAS)]
    r1 = ronda(dec, est)
    dec_I = [dict(d, precio=d['precio'] * I, publicidad=d['publicidad'] * I,
                  costo_investigacion=d['costo_investigacion'] * I) for d in dec]
    est_I = [dict(e, valor_stock_inicial=e['valor_stock_inicial'] * I) for e in est]
    rI = ronda(dec_I, est_I, indice=I)
    for a, b in zip(r1['empresas'], rI['empresas']):
        assert abs(a['unidades'] - b['unidades']) < 1e-6, 'la inflación pareja no cambia las unidades'
        assert abs(a['resultado'] * I - b['resultado']) < 1e-3, 'los resultados escalan con el índice'

    # Precio promedio ponderado: 1000 u. a $1200 + 1000 u. producidas a $1500 -> $1350.
    est = [dict(stock_inicial=1000, valor_stock_inicial=1_200_000, stock_publicidad_anterior=0)
           for _ in range(N_EMPRESAS)]
    dec2 = [dict(precio=pref * 1.25, publicidad=0, produccion=1000) for _ in range(N_EMPRESAS)]
    r = ronda(dec2, est, indice=1.25, tasa_financiera=0.1)
    x = r['empresas'][0]
    assert abs(x['costo_unitario'] - 1350) < 1e-9
    assert abs(x['costo_ventas'] - x['unidades'] * 1350) < 1e-6
    assert abs(x['costo_financiero'] - 0.1 * x['valor_stock_final']) < 1e-6

    # Reparto de equipos en mercados: parejos y sin superar el tamaño objetivo.
    assert mercado.repartir_mercados(10, 4) == [4, 3, 3]
    assert mercado.repartir_mercados(8, 4) == [4, 4]
    assert mercado.repartir_mercados(9, 4) == [3, 3, 3]
    assert mercado.repartir_mercados(7, 4) == [4, 3]
    assert mercado.repartir_mercados(3, 4) == [3]
    assert mercado.repartir_mercados(13, 5) == [5, 4, 4]
    for total in range(1, 41):
        for objetivo in range(1, 9):
            t = mercado.repartir_mercados(total, objetivo)
            assert sum(t) == total and max(t) <= objetivo and max(t) - min(t) <= 1
    assert mercado.demanda_del_mercado(10_000, 3) == 30_000

    # Moneda constante: $100 de un trimestre con índice 1 valen $110 si el índice pasa a 1,1.
    assert abs(mercado.acumular_constante(100, 1.0, 50, 1.1) - 160) < 1e-9
    print('   OK: logit, publicidad acumulada, faltantes, stock y baja final, estacionalidad,\n'
          '       neutralidad de la inflación, PPP, costo financiero y moneda constante.\n')


def informe_equilibrio(cfg):
    lam = cfg['retencion_publicidad']
    print('2) Equilibrio simétrico en estado estacionario (trimestre promedio)')
    p, a = equilibrio_simetrico(cfg)
    r = resultado_de(0, iguales(p, a), cfg)
    margen = (p - cfg['costo_variable']) / p
    print(f'   Precio:            $ {fmt(p)}  (margen sobre precio {margen:.0%})')
    print(f'   Publicidad:        $ {fmt(a)} por trimestre  (stock publicitario $ {fmt(a / (1 - lam))})')
    print(f'   Unidades/empresa:  {fmt(r["unidades"])}   (capacidad {fmt(cfg["capacidad"])})')
    f = mercado.factores_estacionales(cfg['estacionalidad'])
    print(f'   Unidades por estación: ' + ', '.join(f'T{i + 1} {fmt(r["unidades"] * x)}' for i, x in enumerate(f)))
    print(f'   Resultado:         $ {fmt(r["resultado"])} por trimestre\n')
    return p, a, r


def informe_extremos(cfg, p_eq, a_eq, res_eq):
    print('3) Una empresa se desvía (las otras 3 en equilibrio, estado estacionario)')
    casos = [
        ('Equilibrio (referencia)', p_eq, a_eq),
        ('Precio -20 %', p_eq * 0.8, a_eq),
        ('Precio +20 %', p_eq * 1.2, a_eq),
        ('Sin publicidad', p_eq, 0),
        ('Publicidad máxima', p_eq, cfg['publicidad_max']),
        ('Premium (caro + publicidad máx.)', p_eq * 1.3, cfg['publicidad_max']),
    ]
    print(f'   {"Estrategia":34} {"Precio":>9} {"Publicidad":>12} {"Partic.":>8} {"Resultado":>14} {"vs eq.":>8}')
    for nombre, p, a in casos:
        dec = iguales(p_eq, a_eq)
        dec[0] = dict(precio=p, publicidad=a)
        r = resultado_de(0, dec, cfg)
        dif = (r['resultado'] - res_eq) / abs(res_eq) if res_eq else 0
        print(f'   {nombre:34} {fmt(p):>9} {fmt(a):>12} {r["preferencia"]:>8.1%} '
              f'{fmt(r["resultado"]):>14} {dif:>+8.0%}')
    print()


def informe_produccion(cfg, p_eq, a_eq, r_eq):
    tasa = cfg['inflacion_media'] + cfg['tasa_real']
    print('4) Errores de producción (todas en equilibrio de precio y publicidad, trimestre promedio)')
    print(f'   Penalidad por unidad sobrante y trimestre: almacenamiento $ {fmt(cfg["costo_almacenamiento"])}'
          f' + costo financiero {tasa:.0%} × $ {fmt(cfg["costo_variable"])}'
          f' = $ {fmt(cfg["costo_almacenamiento"] + tasa * cfg["costo_variable"])}')
    u = r_eq['unidades']
    lam = cfg['retencion_publicidad']
    estados = [dict(stock_inicial=0, stock_publicidad_anterior=lam * a_eq / (1 - lam))
               for _ in range(N_EMPRESAS)]
    print(f'   {"Producción de la empresa 0":30} {"Vendidas":>9} {"Stock final":>12} {"Resultado":>14}   Rivales (c/u)')
    for nombre, prod in [('Exacta', u), ('-30 % (se queda corta)', u * 0.7),
                         ('+30 % (le sobra)', u * 1.3), ('+30 %, último trimestre', u * 1.3)]:
        dec = [dict(precio=p_eq, publicidad=a_eq, produccion=u * 1.5) for _ in range(N_EMPRESAS)]
        dec[0]['produccion'] = prod
        r = mercado.simular_ronda(dec, estados, cfg, ultima_ronda='último' in nombre,
                                  tasa_financiera=tasa)
        e0, e1 = r['empresas'][0], r['empresas'][1]
        # A los rivales no se les cobra el stock sobrante en esta comparación.
        rival = e1['resultado'] + e1['costo_almacenamiento'] + e1['costo_financiero'] + e1['baja_stock']
        print(f'   {nombre:30} {fmt(e0["unidades"]):>9} {fmt(e0["stock_final"]):>12} '
              f'{fmt(e0["resultado"]):>14}   {fmt(rival)}')
    print()


def informe_partidas(cfg, partidas=500, semilla=1):
    print(f'5) {partidas} partidas de {cfg["num_rondas"]} trimestres con decisiones aleatorias "razonables"')
    rnd = random.Random(semilla)
    f = mercado.factores_estacionales(cfg['estacionalidad'])
    finales, faltantes, stocks = [], 0, []
    total = 0
    indices_finales = []
    for _ in range(partidas):
        estados = [dict(stock_inicial=cfg['stock_inicial'], stock_publicidad_anterior=0)
                   for _ in range(N_EMPRESAS)]
        acum = [0.0] * N_EMPRESAS   # en moneda constante (pesos del trimestre corriente)
        indice = indice_ant = 1.0
        for ronda in range(1, int(cfg['num_rondas']) + 1):
            t = mercado.trimestre_del_anio(ronda, int(cfg['trimestre_inicial']))
            shock = max(-2, min(2, rnd.gauss(0, 1))) * cfg['desvio_shock']
            infl = 0.0 if ronda == 1 else max(0.0, cfg['inflacion_media']
                                               + max(-2, min(2, rnd.gauss(0, 1))) * cfg['inflacion_desvio'])
            indice = mercado.siguiente_indice(indice_ant, infl)
            tasa = (infl if ronda > 1 else cfg['inflacion_media']) + cfg['tasa_real']
            # Decisiones "razonables" en términos reales, expresadas en pesos del trimestre.
            dec = [dict(precio=rnd.uniform(1500, 3500) * indice,
                        publicidad=rnd.uniform(0, 5_000_000) * indice,
                        produccion=rnd.uniform(6000, 16000)) for _ in range(N_EMPRESAS)]
            r = mercado.simular_ronda(dec, estados, cfg, f[t - 1] * (1 + shock),
                                      ultima_ronda=(ronda == cfg['num_rondas']),
                                      indice=indice, tasa_financiera=tasa)
            for i, e in enumerate(r['empresas']):
                acum[i] = mercado.acumular_constante(acum[i], indice_ant, e['resultado'], indice)
                faltantes += e['faltante'] > 1
                total += 1
                stocks.append(e['stock_final'])
                estados[i] = dict(stock_inicial=e['stock_final'], valor_stock_inicial=e['valor_stock_final'],
                                  stock_publicidad_anterior=e['stock_publicidad'])
            indice_ant = indice
        # Para comparar con versiones anteriores, se expresa en pesos del primer trimestre.
        finales.extend(a / indice for a in acum)
        indices_finales.append(indice)
    q = statistics.quantiles(finales, n=10)
    print(f'   Inflación acumulada media: {statistics.mean(indices_finales) - 1:.0%}. '
          f'Resultados en pesos constantes del primer trimestre.')
    print(f'   Resultado acumulado: mediana $ {fmt(statistics.median(finales))}, '
          f'P10 $ {fmt(q[0])}, P90 $ {fmt(q[-1])}')
    print(f'   Empresas que terminan con pérdida: {sum(x < 0 for x in finales) / len(finales):.0%}')
    print(f'   Trimestres con faltantes: {faltantes / total:.0%}   '
          f'Stock final medio: {fmt(statistics.mean(stocks))} u.\n')


def main():
    cfg = leer_parametros(sys.argv[1:])
    print('Parámetros:', {k: cfg[k] for k in mercado.PARAMETROS}, '\n')
    verificaciones(cfg)
    p, a, r = informe_equilibrio(cfg)
    informe_extremos(cfg, p, a, r['resultado'])
    informe_produccion(cfg, p, a, r)
    informe_partidas(cfg)


if __name__ == '__main__':
    main()
