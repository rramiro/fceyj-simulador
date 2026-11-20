"""
Verifica que el catálogo de juegos (_static/juegos/catalogo.json) coincida con settings.py.

    python scripts/verificar_catalogo.py

- Cada juego 'disponible' tiene su SESSION_CONFIG, con la app en app_sequence, y
  todos los campos y parámetros que el tablero deja cambiar existen en la configuración.
- Cada SESSION_CONFIG figura en el catálogo (si no, el tablero no la mostraría).
- Las salas del catálogo son las ROOMS de settings.py.

No importa oTree: lee settings.py por ruta.
"""
import importlib.util
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def cargar_settings():
    spec = importlib.util.spec_from_file_location('settings', RAIZ / 'settings.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def problemas():
    settings = cargar_settings()
    catalogo = json.loads((RAIZ / '_static' / 'juegos' / 'catalogo.json').read_text(encoding='utf-8'))
    configs = {c['name']: c for c in settings.SESSION_CONFIGS}
    errores = []

    for juego in catalogo['juegos']:
        nombre = juego['config']
        if juego['estado'] not in ('disponible', 'proximamente'):
            errores.append(f'{nombre}: estado desconocido "{juego["estado"]}"')
        if juego['estado'] != 'disponible':
            continue
        cfg = configs.get(nombre)
        if cfg is None:
            errores.append(f'{nombre}: no hay SESSION_CONFIG con ese nombre')
            continue
        if juego['app'] not in cfg['app_sequence']:
            errores.append(f'{nombre}: la app {juego["app"]} no está en app_sequence')
        claves = [juego['rondas']['campo']] if juego.get('rondas') else []
        if juego.get('grupo', {}).get('campo'):
            claves.append(juego['grupo']['campo'])
        claves += [c['clave'] for c in juego.get('campos', [])]
        claves += [p['clave'] for p in juego.get('parametros', [])]
        for clave in claves:
            if clave not in cfg:
                errores.append(f'{nombre}: "{clave}" no está en su SESSION_CONFIG')

    en_catalogo = {j['config'] for j in catalogo['juegos'] if j['estado'] == 'disponible'}
    for nombre in configs:
        if nombre not in en_catalogo:
            errores.append(f'SESSION_CONFIG {nombre} no figura como disponible en el catálogo')

    salas = {s['nombre'] for s in catalogo['salas']}
    rooms = {r['name'] for r in settings.ROOMS}
    if salas != rooms:
        errores.append(f'salas del catálogo {sorted(salas)} distintas de ROOMS {sorted(rooms)}')
    return errores


if __name__ == '__main__':
    errores = problemas()
    for e in errores:
        print('ERROR:', e)
    print('Catálogo OK' if not errores else f'{len(errores)} problema(s) en el catálogo')
    sys.exit(1 if errores else 0)
