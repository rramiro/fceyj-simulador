"""
Verificaciones y calibración del juego "El depósito" (deposito/modelo.py).

    python scripts/simular_deposito.py
    python scripts/simular_deposito.py costo_faltante=80000 demora_max=8     # probar otros valores

1) Verificaciones: fórmulas de la cátedra (ej. ServiMed 2.2), conservación del stock, el descuento.
2) Estrategias típicas en muchas partidas: costo de gestión, faltantes, órdenes y quién gana.
"""
import importlib.util
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from deposito import modelo  # noqa: E402

PARAMETROS_DEFECTO = dict(
    num_rondas=6,
    dias_mes=25,
    dias_anio=300,
    demanda_diaria=8,
    escala_demanda=1.0,
    demora_min=2,
    demora_max=6,
    precio=400_000,
    costo_orden=150_000,
    tasa_anual=0.24,
    costo_faltante=60_000,
    stock_inicial=100,
    descuento=0.03,
    suba_co=0.15,
    suba_demanda=0.5,
    demora_extra_huelga=4,
    tasa_alta=0.48,
    tolerancia_pregunta=0.05,
    puntos_pregunta=5,
    puntos_resultado=70,
)
PARTIDAS = 1000


def cargar_parametros():
    """La configuración 'deposito' de settings.py si existe; si no, los valores de arriba."""
    spec = importlib.util.spec_from_file_location('settings', RAIZ / 'settings.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg = next((c for c in mod.SESSION_CONFIGS if c['name'] == 'deposito'), None)
    if not cfg:
        return dict(PARAMETROS_DEFECTO)
    return {k: cfg[k] for k in ['num_rondas'] + modelo.PARAMETROS}


def leer_parametros(argv):
    cfg = cargar_parametros()
    for arg in argv:
        clave, valor = arg.split('=')
        if clave not in cfg:
            sys.exit(f'Parámetro desconocido: {clave}')
        cfg[clave] = float(valor)
    return cfg


def millones(x):
    return f'{x / 1e6:,.1f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def pct(x):
    return f'{x * 100:.0f} %'


# --- Estrategias: cada una devuelve (n, R) para el mes -------------------------------------------

def de_manual(mes, p, esc):
    return modelo.politica_recomendada(mes, p, esc)


def n0_sin_proteccion(mes, p, esc):
    f = modelo.formulas(mes, p, esc)
    return round(f['n0']), round(f['demanda_demora_media'])


def n0_fijo_sin_eventos(mes, p, esc):
    """n0 y R del primer mes, sin ajustar a los eventos."""
    return modelo.politica_recomendada(1, p, esc)


def pide_mucho(mes, p, esc):
    return 400, 50


def pide_seguido(mes, p, esc):
    return 15, 50


def mucha_proteccion(mes, p, esc):
    n, _ = modelo.politica_recomendada(mes, p, esc)
    f = modelo.formulas(mes, p, esc)
    return n, round(2 * f['demanda_demora_max'])


ESTRATEGIAS = {
    'De manual (n0, R = demanda en la demora máx.)': de_manual,
    'n0 sin stock de protección': n0_sin_proteccion,
    'n0 del primer mes, sin mirar eventos': n0_fijo_sin_eventos,
    'Mucha protección (R al doble)': mucha_proteccion,
    'Pide mucho (n = 400)': pide_mucho,
    'Pide seguido (n = 15)': pide_seguido,
}


def jugar(estrategia, esc, p):
    est = modelo.estado_inicial(p)
    res = []
    for mes in range(1, int(p['num_rondas']) + 1):
        n, r = estrategia(mes, p, esc)
        est, rm = modelo.simular_mes(mes, n, r, est, p, esc)
        res.append(rm)
    return est, res


# --- Verificaciones ----------------------------------------------------------------------------------

def verificaciones(p):
    # ServiMed (guía 2.2): D = 2000, co = 30, cm = 40 → n0 = √(2·30·2000/40) ≈ 54,8.
    assert abs(modelo.lote_optimo(30, 2000, 40) - 54.77) < 0.01
    esc = modelo.generar_escenario(p, int(p['num_rondas']), 7)
    assert modelo.generar_escenario(p, int(p['num_rondas']), 7) == esc, 'la semilla no reproduce el escenario'
    # Conservación: stock inicial + recibido − vendido = stock final, en cada mes y estrategia.
    for s in range(200):
        e = modelo.generar_escenario(p, int(p['num_rondas']), s)
        for f in ESTRATEGIAS.values():
            est = modelo.estado_inicial(p)
            for mes in range(1, int(p['num_rondas']) + 1):
                antes = est['stock']
                n, r = f(mes, p, e)
                est, rm = modelo.simular_mes(mes, n, r, est, p, e)
                recibido = sum(x['llegan'] for x in rm['serie'])
                assert antes + recibido - rm['vendidas'] == rm['stock_final'], (s, mes)
                assert rm['vendidas'] + rm['perdidas'] == rm['demanda']
                for o in rm['ordenes']:
                    d = modelo.datos_mes(mes, p, e)
                    assert d['demora_min'] <= o['llega'] - o['dia'] <= d['demora_max']
    # La pregunta del mes con su propio valor se acierta.
    for mes in range(1, int(p['num_rondas']) + 1):
        _, v, _ = modelo.pregunta_del_mes(mes, p, esc)
        assert modelo.acierta(v, v, p)
    print('Verificaciones: OK\n')


def informe(p):
    f = modelo.formulas(1, p, modelo.generar_escenario(p, 1, 1))
    print(f'Mes normal: D = {p["demanda_diaria"] * p["dias_anio"]:.0f} u/año; n0 = {f["n0"]:.0f}; h0 = {f["h0"]:.1f} '
          f'órdenes/año; t0 = {f["t0"]:.1f} días; CT0 = $ {millones(f["ct0"])} M/año; '
          f'demanda en la demora: media {f["demanda_demora_media"]:.0f}, máx. {f["demanda_demora_max"]:.0f}; '
          f'cm = $ {f["cm_anual"] / p["dias_anio"]:,.0f} por unidad y día.\n'.replace(',', '.'))

    partidas = [modelo.generar_escenario(p, int(p['num_rondas']), s) for s in range(PARTIDAS)]
    res = {n: [jugar(f, e, p) for e in partidas] for n, f in ESTRATEGIAS.items()}
    gana = dict.fromkeys(res, 0)
    for k in range(PARTIDAS):
        gana[min(res, key=lambda n: res[n][k][0]['costo_acumulado'])] += 1
    print(f'Estrategias ({PARTIDAS} partidas de {int(p["num_rondas"])} meses; costos acumulados en millones de pesos):')
    print(f'   {"Estrategia":<46} {"costo":>7} {"órdenes":>8} {"mantener":>9} {"faltantes":>10} {"descuento":>10} '
          f'{"servicio":>9} {"puntaje":>8} {"gana":>6}')
    costos_medios = {n: statistics.mean(r[0]['costo_acumulado'] for r in v) for n, v in res.items()}
    puntos = dict(zip(costos_medios, modelo.puntaje_final(list(costos_medios.values()), [0] * len(costos_medios), p)))
    for n, v in res.items():
        meses = [m for _, ms in v for m in ms]
        suma = lambda k: statistics.mean(sum(m[k] for m in ms) for _, ms in v)  # noqa: E731
        servicio = sum(m['vendidas'] for m in meses) / max(1, sum(m['demanda'] for m in meses))
        print(f'   {n:<46} {millones(costos_medios[n]):>7} {millones(suma("costo_ordenes")):>8} '
              f'{millones(suma("costo_mantener")):>9} {millones(suma("costo_faltantes")):>10} '
              f'{millones(suma("ahorro_descuento")):>10} {pct(servicio):>9} {puntos[n]:>8.1f} {pct(gana[n] / PARTIDAS):>6}')
    print('   (puntaje = 70 × costo relativo entre estas estrategias; "gana" = menor costo en la partida)\n')

    # Cuánto mejora la mejor política fija (búsqueda en grilla) frente a la de manual, en mes normal.
    mejor = None
    for n in range(40, 201, 10):
        for r in range(24, 81, 4):
            c = statistics.mean(jugar(lambda m, p_, e_: (n, r), e, p)[0]['costo_acumulado'] for e in partidas[:150])
            if mejor is None or c < mejor[0]:
                mejor = (c, n, r)
    manual = statistics.mean(jugar(de_manual, e, p)[0]['costo_acumulado'] for e in partidas[:150])
    print(f'Mejor política fija (grilla, 150 partidas): n = {mejor[1]}, R = {mejor[2]}, costo $ {millones(mejor[0])} M; '
          f'de manual: $ {millones(manual)} M.')


def main():
    p = leer_parametros(sys.argv[1:])
    print('Parámetros:', p, '\n')
    verificaciones(p)
    informe(p)


if __name__ == '__main__':
    main()
