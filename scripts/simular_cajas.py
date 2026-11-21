"""
Verificaciones y calibración del juego "Las cajas del súper" (cajas/modelo.py).

    python scripts/simular_cajas.py
    python scripts/simular_cajas.py costo_espera=30000 minutos_atencion=6     # probar otros valores

1) Verificaciones: fórmulas M/M/s contra la guía (banco 4.1, Pizza Pampita III.1), reproducibilidad,
   conservación de clientes y que la simulación con muchas horas coincide con el modelo.
2) Estrategias típicas en muchas partidas: costo de cajas, costo de espera, espera media y quién gana.
"""
import importlib.util
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from cajas import modelo  # noqa: E402

PARAMETROS_DEFECTO = dict(
    num_rondas=8,
    llegadas_manana=40,
    llegadas_mediodia=80,
    llegadas_tarde=60,
    llegadas_noche=100,
    escala_llegadas=1.0,
    minutos_atencion=5,
    costo_caja=15_000,
    costo_espera=20_000,
    max_cajas=15,
    efecto_lluvia=-0.25,
    efecto_promocion=0.30,
    efecto_partido=-0.40,
    lentitud_nuevo=0.30,
    lentitud_falla=0.20,
    tolerancia_pregunta=0.05,
    puntos_pregunta=5,
    puntos_resultado=70,
)
PARTIDAS = 1000


def cargar_parametros():
    """La configuración 'cajas' de settings.py si existe; si no, los valores de arriba."""
    spec = importlib.util.spec_from_file_location('settings', RAIZ / 'settings.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg = next((c for c in mod.SESSION_CONFIGS if c['name'] == 'cajas'), None)
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


def miles(x):
    return f'{x / 1e3:,.0f}'.replace(',', '.')


def pct(x):
    return f'{x * 100:.0f} %'


# --- Estrategias: cada una devuelve las cajas de la ronda ----------------------------------------

def de_manual(r, p, esc):
    return modelo.cajas_recomendadas(r, p, esc)


def sin_mirar_eventos(r, p, esc):
    """El óptimo del modelo con la λ de la franja sin evento."""
    base = dict(esc, eventos=['normal'] * len(esc['eventos']))
    return modelo.cajas_recomendadas(r, p, base)


def una_menos(r, p, esc):
    return max(1, de_manual(r, p, esc) - 1)


def dos_mas(r, p, esc):
    return de_manual(r, p, esc) + 2


def minimo_estable(r, p, esc):
    """La menor cantidad de cajas con ρ < 1."""
    return modelo.formulas(r, p, esc)['s_min']


def rho_085(r, p, esc):
    """Regla práctica: la menor cantidad de cajas con ρ ≤ 0,85."""
    d = modelo.datos_ronda(r, p, esc)
    s = 1
    while d['lam'] / (s * d['mu']) > 0.85:
        s += 1
    return s


def fijo_8(r, p, esc):
    return 8


ESTRATEGIAS = {
    'De manual (s óptimo del modelo)': de_manual,
    'Óptimo sin mirar eventos': sin_mirar_eventos,
    'Regla ρ ≤ 0,85': rho_085,
    'Una caja menos que el óptimo': una_menos,
    'Dos cajas más que el óptimo': dos_mas,
    'Mínimo estable (ρ < 1)': minimo_estable,
    '8 cajas todo el día': fijo_8,
}


def jugar(estrategia, esc, p):
    est = modelo.estado_inicial(p)
    res = []
    for r in range(1, int(p['num_rondas']) + 1):
        est, rr = modelo.simular_ronda(r, estrategia(r, p, esc), est, p, esc)
        res.append(rr)
    return est, res


# --- Verificaciones ----------------------------------------------------------------------------------

def verificaciones(p):
    # Banco 4.1: λ = 3/min, μ = 1/min, s = 4 → P0 = 0,0377; Lq = 1,528; Wq = 0,509 min; Pw = 0,509.
    m = modelo.mms(3, 1, 4)
    assert abs(m['p0'] - 0.0377) < 1e-3 and abs(m['lq'] - 1.528) < 1e-3 and abs(m['pw'] - 0.509) < 1e-3, m
    # Quantum 3.2 (M/M/1): λ = 7,5/h, μ = 12/h → Ls = 1,6667; Lq = 1,0417.
    m = modelo.mms(7.5, 12, 1)
    assert abs(m['ls'] - 1.6667) < 1e-4 and abs(m['lq'] - 1.0417) < 1e-4
    # Pizza Pampita III.1 alternativa 3: λ = 24/h, μ = 30/h, s = 2 → P0 = 0,4286; Lq = 0,1524.
    m = modelo.mms(24, 30, 2)
    assert abs(m['p0'] - 0.4286) < 1e-4 and abs(m['lq'] - 0.1524) < 1e-4
    assert modelo.mms(30, 10, 3) is None

    n = int(p['num_rondas'])
    esc = modelo.generar_escenario(p, n, 7)
    assert modelo.generar_escenario(p, n, 7) == esc, 'la semilla no reproduce el escenario'
    # Conservación: los clientes que entran salen el mismo sábado; nadie se pierde entre franjas.
    for s in range(100):
        e = modelo.generar_escenario(p, n, s)
        for f in ESTRATEGIAS.values():
            est = modelo.estado_inicial(p)
            entraron = salieron = 0
            for r in range(1, n + 1):
                previos = len(est['fila']) + len(est['en_caja'])
                est, rr = modelo.simular_ronda(r, f(r, p, e), est, p, e)
                entraron += rr['llegaron']
                assert previos + rr['llegaron'] >= rr['quedan']
                if rr['franja'] == len(modelo.FRANJAS) - 1:
                    assert rr['quedan'] == 0, (s, r)
    # Con muchas horas y sin eventos, la simulación reproduce Ls y Wq del modelo (unidad 5 vs unidad 4).
    q = dict(p, llegadas_mediodia=80)
    horas = 400
    largo = dict(p, **{'llegadas_mediodia': 80})
    import random
    rnd = random.Random(3)
    datos = dict(llegadas=[], trabajo=[])
    t = 0.0
    while True:
        t += rnd.expovariate(80 / 60)
        if t >= horas * 60:
            break
        datos['llegadas'].append(t)
        datos['trabajo'].append(rnd.expovariate(1))
    esc_largo = dict(eventos=['normal', 'normal'], rondas=[dict(llegadas=[], trabajo=[]), datos])
    modelo.FRANJAS[1]['horas'], h0 = horas, modelo.FRANJAS[1]['horas']
    try:
        _, rr = modelo.simular_ronda(2, 9, modelo.estado_inicial(q), largo, esc_largo)
    finally:
        modelo.FRANJAS[1]['horas'] = h0
    teo = modelo.mms(80, 60 / p['minutos_atencion'], 9)
    print(f'Simulación de {horas} h, λ = 80, s = 9: Ls {rr["ls_observada"]:.2f} (modelo {teo["ls"]:.2f}); '
          f'Wq {rr["wq_observada"]:.2f} min (modelo {teo["wq"] * 60:.2f}); '
          f'Pw {rr["pw_observada"]:.2f} (modelo {teo["pw"]:.2f})')
    assert abs(rr['ls_observada'] - teo['ls']) / teo['ls'] < 0.05
    for r in range(1, n + 1):
        _, v, _ = modelo.pregunta_de_la_ronda(r, p, esc)
        assert modelo.acierta(v, v, p)
    print('Verificaciones: OK\n')


def informe(p):
    n = int(p['num_rondas'])
    print('Modelo por franja, sin eventos (miles de $ por hora):')
    base = dict(eventos=['normal'] * 4)
    for r in range(1, 5):
        d = modelo.datos_ronda(r, p, base)
        f = modelo.formulas(r, p, base)
        vecinos = [c for c in f['curva'] if c['estable'] and abs(c['s'] - f['s_opt']) <= 2]
        txt = '  '.join(f's={c["s"]}: {miles(c["costo"])} ({c["wq_min"]:.1f} min)' for c in vecinos)
        print(f'   {d["nombre"]:<9} λ={d["lam"]:>4.0f}  s*={f["s_opt"]:>2}  ρ={f["medidas"]["rho"]:.2f}   {txt}')
    print()

    partidas = [modelo.generar_escenario(p, n, s) for s in range(PARTIDAS)]
    eventos = [e for esc in partidas for e in esc['eventos']]
    print('Eventos:', ', '.join(f'{k} {pct(eventos.count(k) / len(eventos))}' for k in modelo.EVENTOS), '\n')
    res = {nombre: [jugar(f, e, p) for e in partidas] for nombre, f in ESTRATEGIAS.items()}
    gana = dict.fromkeys(res, 0)
    for k in range(PARTIDAS):
        gana[min(res, key=lambda x: res[x][k][0]['costo_acumulado'])] += 1
    costos = {x: statistics.mean(r[0]['costo_acumulado'] for r in v) for x, v in res.items()}
    puntos = dict(zip(costos, modelo.puntaje_final(list(costos.values()), [0] * len(costos), p)))
    print(f'Estrategias ({PARTIDAS} partidas de {n} franjas; costos en miles de pesos):')
    print(f'   {"Estrategia":<34} {"costo":>7} {"cajas":>7} {"espera":>7} {"Wq min":>7} {"Wq máx":>7} '
          f'{"puntaje":>8} {"gana":>6}')
    for x, v in res.items():
        rondas = [rr for _, rs in v for rr in rs]
        suma = lambda k: statistics.mean(sum(rr[k] for rr in rs) for _, rs in v)  # noqa: E731
        wq = statistics.mean(rr['wq_observada'] for rr in rondas)
        wq_max = statistics.mean(max(rr['wq_observada'] for rr in rs) for _, rs in v)
        print(f'   {x:<34} {miles(costos[x]):>7} {miles(suma("costo_cajas")):>7} {miles(suma("costo_espera")):>7} '
              f'{wq:>7.1f} {wq_max:>7.1f} {puntos[x]:>8.1f} {pct(gana[x] / PARTIDAS):>6}')
    print('   (Wq máx = la peor franja de la partida, en promedio; puntaje = 70 × costo relativo; '
          '"gana" = menor costo en la partida)\n')

    # ¿El óptimo del modelo es también el óptimo de la simulación? Grilla de s fijo por franja (sin eventos).
    print('Óptimo simulado por franja sin eventos (200 partidas, mismo s en las 4 franjas del sábado ±):')
    escs = [modelo.generar_escenario(p, 4, 10_000 + s) for s in range(200)]
    escs = [e for e in escs if all(ev == 'normal' for ev in e['eventos'])] or escs
    for r in range(1, 5):
        s_opt = modelo.formulas(r, p, dict(eventos=['normal'] * 4))['s_opt']
        fila = []
        for s in range(max(1, s_opt - 2), s_opt + 3):
            costos_s = []
            for e in escs:
                e = dict(e, eventos=['normal'] * 4)
                est = modelo.estado_inicial(p)
                for rr_ in range(1, r):
                    est, _ = modelo.simular_ronda(rr_, modelo.cajas_recomendadas(rr_, p, e), est, p, e)
                _, rr = modelo.simular_ronda(r, s, est, p, e)
                costos_s.append(rr['costo'])
            fila.append(f's={s}: {miles(statistics.mean(costos_s))}')
        print(f'   {modelo.FRANJAS[r - 1]["nombre"]:<9} (modelo s*={s_opt})  ' + '  '.join(fila))


def main():
    p = leer_parametros(sys.argv[1:])
    print('Parámetros:', p, '\n')
    verificaciones(p)
    informe(p)


if __name__ == '__main__':
    main()
