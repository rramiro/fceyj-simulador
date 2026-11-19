"""
Verificaciones y calibración del modelo de cartera (cartera/modelo.py).

    python scripts/simular_cartera.py
    python scripts/simular_cartera.py acciones_desvio=0.06 prob_crisis=0.05   # probar otros valores

1) Verificaciones: identidades contables (comisión, rebalanceo, valores reales).
2) Mercado: rendimiento real y riesgo de cada activo por separado.
3) Estrategias: muchas partidas con estrategias típicas de los equipos; para cada una,
   rentabilidad real (TEA), volatilidad, Sharpe, caída máxima y cuántas veces gana.
"""
import importlib.util
import random
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))   # nucleo/ y cartera/ sin importar oTree

from cartera import modelo  # noqa: E402

def cargar_settings():
    spec = importlib.util.spec_from_file_location('settings', RAIZ / 'settings.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Los parámetros salen de la configuración 'cartera' de settings.py (un solo lugar).
_CONFIG = next(c for c in cargar_settings().SESSION_CONFIGS if c['name'] == 'cartera')
PARAMETROS = {k: _CONFIG[k] for k in modelo.PARAMETROS}
TRIMESTRES = _CONFIG['num_rondas']
PARTIDAS = 2000


def leer_parametros(argv):
    cfg = dict(PARAMETROS)
    for arg in argv:
        clave, valor = arg.split('=')
        if clave not in cfg:
            sys.exit(f'Parámetro desconocido: {clave}')
        cfg[clave] = float(valor)
    return cfg


def pct(x, dec=1):
    return f'{x * 100:,.{dec}f} %'.replace(',', 'X').replace('.', ',').replace('X', '.')


# --- Estrategias típicas -------------------------------------------------------------
# Cada una recibe (trimestre, escenario hasta el trimestre anterior, titular del trimestre)
# y devuelve los porcentajes (acciones, bonos, liquidez).

def fija(pesos):
    return lambda t, pasado, noticia: pesos


def sigue_noticias(t, pasado, noticia):
    return (0.70, 0.20, 0.10) if noticia == 'optimista' else (0.10, 0.40, 0.50)


def persigue_rendimiento(t, pasado, noticia):
    """Todo al activo que más rindió el trimestre anterior (mucho rebalanceo)."""
    if not pasado:
        return (0.35, 0.35, 0.30)
    r = pasado[-1]['rendimientos']
    mejor = max(modelo.ACTIVOS, key=lambda a: r[a])
    return tuple(1.0 if a == mejor else 0.0 for a in modelo.ACTIVOS)


def al_azar(rnd):
    def elegir(t, pasado, noticia):
        a = rnd.randrange(0, 21)
        b = rnd.randrange(0, 21 - a)
        return (a / 20, b / 20, (20 - a - b) / 20)
    return elegir


ESTRATEGIAS = {
    'Todo liquidez': fija((0, 0, 1)),
    'Todo bonos': fija((0, 1, 0)),
    'Todo acciones': fija((1, 0, 0)),
    'Equilibrada 60/30/10': fija((0.6, 0.3, 0.1)),
    'Tercios 35/35/30': fija((0.35, 0.35, 0.30)),
    'Conservadora 20/50/30': fija((0.2, 0.5, 0.3)),
    'Sigue las noticias': sigue_noticias,
    'Persigue el rendimiento': persigue_rendimiento,
}


def jugar(estrategia, escenario, cfg):
    decisiones = [estrategia(t, escenario[:t - 1], escenario[t - 1]['noticia']) for t in range(1, len(escenario) + 1)]
    return modelo.evaluar(modelo.simular_cartera(decisiones, escenario, cfg), escenario, cfg)


# --- 1) Verificaciones -------------------------------------------------------------------

def verificaciones(cfg):
    esc = modelo.generar_escenario(cfg, TRIMESTRES, semilla=7)
    assert modelo.generar_escenario(cfg, TRIMESTRES, semilla=7) == esc, 'la semilla no reproduce el escenario'

    # Sin comisión y todo en liquidez: el valor crece exactamente a la tasa del plazo fijo.
    sin_com = dict(cfg, comision=0.0)
    filas = modelo.simular_cartera([(0, 0, 1)] * TRIMESTRES, esc, sin_com)
    esperado = cfg['capital_inicial'] * (1 + cfg['inflacion_media'] + cfg['liquidez_diferencial']) ** TRIMESTRES
    assert abs(filas[-1]['valor_final'] - esperado) < 1e-3

    # Pasar de liquidez a acciones paga comisión sobre lo comprado y el total cierra.
    montos, costo = modelo.rebalancear([0, 0, 1000.0], (1, 0, 0), 0.005)
    assert abs(sum(montos) + costo - 1000) < 1e-6 and abs(costo - 0.005 * montos[0]) < 1e-6
    # Quedarse en liquidez no paga nada.
    assert modelo.rebalancear([0, 0, 1000.0], (0, 0, 1), 0.005)[1] == 0

    # Los porcentajes se validan.
    assert modelo.validar_porcentajes((0.6, 0.3, 0.1)) is None
    assert modelo.validar_porcentajes((0.6, 0.3, 0.2)) is not None
    assert modelo.validar_porcentajes((0.62, 0.28, 0.1)) is not None

    # Valor real = nominal / índice y TEA de un año entero = rentabilidad del año.
    filas = modelo.simular_cartera([(0.6, 0.3, 0.1)] * 4, esc[:4], cfg)
    assert abs(filas[-1]['valor_real'] - filas[-1]['valor_final'] / esc[3]['indice']) < 1e-6
    ev = modelo.evaluar(filas, esc[:4], cfg)
    assert abs(ev['tea_real'] - ev['anios'][0]['rentabilidad_real']) < 1e-9
    print('Verificaciones: OK\n')


# --- 2) Mercado -------------------------------------------------------------------------

def informe_mercado(cfg, escenarios):
    print(f'Mercado ({PARTIDAS} escenarios de {TRIMESTRES} trimestres). Rendimientos REALES (descontada la inflación):')
    print(f'   {"Activo":<10} {"media trim.":>12} {"≈ anual":>9} {"desvío anual":>13} {"trim. negativos":>16}')
    for a in modelo.ACTIVOS:
        reales = [(1 + d['rendimientos'][a]) / (1 + d['inflacion']) - 1 for e in escenarios for d in e]
        m = statistics.mean(reales)
        print(f'   {a:<10} {pct(m, 2):>12} {pct((1 + m) ** 4 - 1):>9} {pct(statistics.stdev(reales) * 2):>13} '
              f'{pct(sum(r < 0 for r in reales) / len(reales), 0):>16}')
    crisis = sum(d['crisis'] for e in escenarios for d in e) / (PARTIDAS * TRIMESTRES)
    con_crisis = sum(any(d['crisis'] for d in e) for e in escenarios) / PARTIDAS
    normal = cfg['acciones_media'] - cfg['prob_crisis'] * cfg['crisis_acciones']
    aciertos = [d['noticia'] == ('optimista' if not d['crisis'] and d['acciones_usd'] >= normal else 'pesimista')
                for e in escenarios for d in e]
    infl = [e[-1]['indice'] ** (4 / TRIMESTRES) - 1 for e in escenarios]
    print(f'   Inflación anual media: {pct(statistics.mean(infl))}.  Trimestres con crisis: {pct(crisis)}; '
          f'partidas con al menos una: {pct(con_crisis, 0)}.  Titulares acertados: {pct(statistics.mean(aciertos), 0)}.\n')


# --- 3) Estrategias -------------------------------------------------------------------------

def informe_estrategias(cfg, escenarios, semilla=1):
    rnd = random.Random(semilla)
    resultados = {n: [jugar(e, esc, cfg) for esc in escenarios] for n, e in ESTRATEGIAS.items()}
    azar = al_azar(rnd)
    resultados['Al azar (cada trimestre)'] = [jugar(azar, esc, cfg) for esc in escenarios]

    # ¿Quién termina primera en cada partida (por TEA real)?
    nombres = list(resultados)
    gana = dict.fromkeys(nombres, 0)
    for k in range(PARTIDAS):
        gana[max(nombres, key=lambda n: resultados[n][k]['tea_real'])] += 1

    print(f'Estrategias ({PARTIDAS} partidas de {TRIMESTRES} trimestres; en pesos constantes salvo la columna en dólares):')
    print(f'   {"Estrategia":<26} {"TEA real":>9} {"P10":>8} {"P90":>8} {"pierde":>7} {"volat.":>7} '
          f'{"Sharpe":>7} {"caída máx.":>10} {"comis.":>7} {"TEA US$":>8} {"gana":>6}')
    for n in nombres:
        r = resultados[n]
        teas = sorted(x['tea_real'] for x in r)
        q = statistics.quantiles(teas, n=10)
        print(f'   {n:<26} {pct(statistics.median(teas)):>9} {pct(q[0]):>8} {pct(q[-1]):>8} '
              f'{pct(sum(t < 0 for t in teas) / PARTIDAS, 0):>7} '
              f'{pct(statistics.median(x["volatilidad"] for x in r)):>7} '
              f'{statistics.median(x["sharpe"] for x in r):>7.2f} '
              f'{pct(statistics.median(x["caida_maxima"] for x in r)):>10} '
              f'{pct(statistics.median(x["comisiones"] for x in r) / cfg["capital_inicial"]):>7} '
              f'{pct(statistics.median(x["tea_dolares"] for x in r)):>8} '
              f'{pct(gana[n] / PARTIDAS, 0):>6}')
    print('   (mediana de las partidas; "pierde" = partidas con TEA real negativa; comisiones sobre el capital inicial;'
          ' "gana" = partidas en las que es la mejor)\n')


def main():
    cfg = leer_parametros(sys.argv[1:])
    print('Parámetros:', cfg, '\n')
    verificaciones(cfg)
    escenarios = [modelo.generar_escenario(cfg, TRIMESTRES, semilla=s) for s in range(PARTIDAS)]
    informe_mercado(cfg, escenarios)
    informe_estrategias(cfg, escenarios)


if __name__ == '__main__':
    main()
