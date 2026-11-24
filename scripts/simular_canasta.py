"""
Verificaciones y calibración del juego "La canasta de Soledad" (canasta/modelo.py).

    python scripts/simular_canasta.py
    python scripts/simular_canasta.py precio_cine=25000      # probar otros valores

1) Verificaciones: en el óptimo continuo TMS = Px/Py, el óptimo entero está a menos de una entrada del
   continuo, la canasta está sobre la recta de presupuesto y la compensación de Slutsky alcanza para la
   canasta de marzo.
2) Por tipo de consumidor: la cantidad óptima de cada mes y los puntos de estrategias típicas.
"""
import importlib.util
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from canasta import modelo  # noqa: E402

PARAMETROS_DEFECTO = dict(
    num_rondas=8, ingreso_base=160_000, precio_cine=20_000, precio_alimentos=10_000,
    puntos_exacto=10, puntos_a_uno=6, puntos_a_dos=2, tolerancia_pregunta=0.05, puntos_pregunta=5,
)


def cargar_parametros():
    spec = importlib.util.spec_from_file_location('settings', RAIZ / 'settings.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg = next((c for c in mod.SESSION_CONFIGS if c['name'] == 'canasta'), None)
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


def verificar(p):
    for tipo in modelo.TIPOS:
        for ronda in range(1, len(modelo.RONDAS) + 1):
            d = modelo.datos_ronda(ronda, p, x_marzo=modelo.optimo(modelo.datos_ronda(1, p), tipo)[0])
            xc = modelo.demanda_continua(d['ingreso'], d['px'], d['py'], tipo)
            yc = modelo.alimentos(xc, d)
            assert abs(modelo.tms(xc, yc, tipo) - d['px'] / d['py']) < 1e-6, (tipo, ronda)
            x, y, u = modelo.optimo(d, tipo)
            assert abs(x - xc) < 1 + 1e-9, (tipo, ronda, x, xc)
            assert abs(d['px'] * x + d['py'] * y - d['ingreso']) < 1e-6
            assert abs(modelo.y_indiferencia(x, u, tipo) - y) < 1e-6 if x > 0 else True
    # Slutsky: con el ingreso compensado alcanza justo para la canasta de marzo.
    for xm in range(0, 9):
        d1, d7 = modelo.datos_ronda(1, p), modelo.datos_ronda(7, p, x_marzo=xm)
        ym = modelo.alimentos(xm, d1)
        assert abs(d7['px'] * xm + d7['py'] * ym - d7['ingreso']) < 1e-6
    # Elasticidad arco del TP: de 4 a 8 entradas cuando el precio baja a la mitad → −1.
    assert abs(modelo.elasticidad_arco(4, 8, 2, 1) + 1) < 1e-9
    print('Verificaciones: OK')


ESTRATEGIAS = {
    'De manual (TMS = Px/Py)': lambda d, tipo, xs, rnd: modelo.optimo(d, tipo)[0],
    'Mitad del ingreso en cine': lambda d, tipo, xs, rnd: int((d['ingreso'] / 2) // d['px']),
    'Misma participación que en marzo': lambda d, tipo, xs, rnd:
        round(xs[0]['x'] * xs[-1]['px0'] / xs[-1]['i0'] * d['ingreso'] / d['px']) if xs else modelo.optimo(d, tipo)[0],
    'Repetir las entradas de marzo': lambda d, tipo, xs, rnd: xs[0]['x'] if xs else modelo.optimo(d, tipo)[0],
    'Al azar': lambda d, tipo, xs, rnd: rnd.randint(0, d['x_max']),
}


def jugar(estrategia, tipo, p, rnd):
    hist = []
    rondas = []
    for ronda in range(1, int(p['num_rondas']) + 1):
        xm = rondas[0]['x'] if rondas else None
        d = modelo.datos_ronda(ronda, p, xm)
        x = ESTRATEGIAS[estrategia](d, tipo, hist, rnd)
        x = max(0, min(int(x), d['x_max']))
        if not hist:
            hist.append(dict(x=x, px0=d['px'], i0=d['ingreso']))
        else:
            hist.append(dict(x=x, px0=hist[0]['px0'], i0=hist[0]['i0']))
        r = modelo.jugar_ronda(ronda, x, None, tipo, p, xm)
        rondas.append(r)
    return rondas


def main():
    p = leer_parametros(sys.argv[1:])
    verificar(p)
    rnd = random.Random(1)
    print()
    for tipo, t in modelo.TIPOS.items():
        d1 = modelo.datos_ronda(1, p)
        x1 = modelo.optimo(d1, tipo)[0]
        print(f'## {t["nombre"]} (a = {t["a"]}, σ = {t["sigma"]})')
        print(f'   {"Mes":<12} {"I":>8} {"Px":>7} {"Py":>7} {"X*":>4} {"X cont.":>8} {"Y*":>6} {"% cine":>7}')
        for ronda in range(1, int(p['num_rondas']) + 1):
            d = modelo.datos_ronda(ronda, p, x1)
            x, y, _ = modelo.optimo(d, tipo)
            xc = modelo.demanda_continua(d['ingreso'], d['px'], d['py'], tipo)
            print(f'   {d["mes"]:<12} {d["ingreso"]:>8,.0f} {d["px"]:>7,.0f} {d["py"]:>7,.0f} {x:>4} {xc:>8.2f} '
                  f'{y:>6.1f} {100 * d["px"] * x / d["ingreso"]:>6.0f}%')
        print(f'   {"Estrategia":<36} {"Puntos (de 80)":>15} {"Ingreso real":>13}')
        for nombre in ESTRATEGIAS:
            reps = 200 if nombre == 'Al azar' else 1
            pts = rel = 0
            for _ in range(reps):
                rs = jugar(nombre, tipo, p, rnd)
                pts += sum(r['puntos'] for r in rs) / reps
                rel += sum(r['relativa'] for r in rs) / len(rs) / reps
            print(f'   {nombre:<36} {pts:>15.1f} {100 * rel:>12.1f}%')
        print()


if __name__ == '__main__':
    main()
