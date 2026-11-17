"""
Huella del esquema de la base de datos de oTree.

oTree no tiene migraciones: si cambian los campos de Subsession, Group o Player
(o la versión de oTree), hay que recrear la base con `otree resetdb`, lo que
borra las sesiones. Este script resume esos campos en una huella para que el
despliegue detecte el cambio antes de reiniciar el servidor.

No importa oTree ni ejecuta el código de las apps: lee los archivos con `ast`.

Uso:
    python scripts/esquema.py            # muestra los campos y la huella
    python scripts/esquema.py --huella   # solo la huella (para los scripts de despliegue)
"""
import ast
import hashlib
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CLASES_BASE = {'BaseSubsession', 'BaseGroup', 'BasePlayer', 'ExtraModel'}


def version_otree():
    texto = (RAIZ / 'requirements.txt').read_text(encoding='utf-8')
    m = re.search(r'^otree\s*==\s*([\w.]+)', texto, re.MULTILINE | re.IGNORECASE)
    return m.group(1) if m else 'sin-fijar'


def campos_de_app(archivo):
    """Líneas 'app.Clase.campo = models.Tipo(...)' de una app."""
    app = archivo.parent.name
    arbol = ast.parse(archivo.read_text(encoding='utf-8'))
    lineas = []
    for nodo in arbol.body:
        if not isinstance(nodo, ast.ClassDef):
            continue
        bases = {b.id for b in nodo.bases if isinstance(b, ast.Name)}
        if not bases & CLASES_BASE:
            continue
        for item in nodo.body:
            if not (isinstance(item, ast.Assign) and isinstance(item.value, ast.Call)):
                continue
            func = item.value.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) \
                    and func.value.id == 'models':
                for destino in item.targets:
                    if isinstance(destino, ast.Name):
                        # Solo el tipo de campo cambia la tabla; las etiquetas y valores iniciales no.
                        lineas.append(f'{app}.{nodo.name}.{destino.id}: {func.attr}')
    return lineas


def campos_de_settings():
    """PARTICIPANT_FIELDS y SESSION_FIELDS también son columnas de la base."""
    arbol = ast.parse((RAIZ / 'settings.py').read_text(encoding='utf-8'))
    lineas = []
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1 \
                and isinstance(nodo.targets[0], ast.Name) \
                and nodo.targets[0].id in ('PARTICIPANT_FIELDS', 'SESSION_FIELDS'):
            for valor in ast.literal_eval(nodo.value):
                lineas.append(f'settings.{nodo.targets[0].id}.{valor}')
    return lineas


def esquema():
    lineas = [f'otree=={version_otree()}'] + campos_de_settings()
    for archivo in sorted(RAIZ.glob('*/__init__.py')):
        if archivo.parent.name.startswith(('.', '_')):
            continue
        lineas += campos_de_app(archivo)
    return sorted(lineas)


def huella(lineas):
    return hashlib.sha256('\n'.join(lineas).encode('utf-8')).hexdigest()[:16]


if __name__ == '__main__':
    lineas = esquema()
    if '--huella' in sys.argv:
        print(huella(lineas))
    else:
        print('\n'.join(lineas))
        print(f'\nHuella: {huella(lineas)}')
