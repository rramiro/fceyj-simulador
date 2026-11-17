#!/usr/bin/env bash
#
# Despliega una imagen del simulador en un ambiente (testing o produccion).
#
# Lo ejecuta GitHub Actions por SSH con el usuario "despliegue", cuya clave está
# restringida a este script (authorized_keys con command=...). También se puede
# correr a mano en el servidor:
#
#     echo "$TOKEN" | /opt/simulador/bin/desplegar.sh testing ghcr.io/usuario/fceyj-simulador:sha-abc1234
#     /opt/simulador/bin/desplegar.sh produccion <imagen> --resetdb
#
# Por la entrada estándar puede recibir un token para bajar la imagen de ghcr.io
# (GitHub Actions manda el GITHUB_TOKEN del trabajo, que vence al terminar).
#
# Códigos de salida: 0 ok · 1 error · 2 uso incorrecto · 3 cambió el esquema en
# producción y hace falta --resetdb (ver el workflow "Recrear base").
#
set -euo pipefail

BASE=/opt/simulador

# Con la clave restringida, los argumentos llegan en SSH_ORIGINAL_COMMAND.
if [[ -n "${SSH_ORIGINAL_COMMAND:-}" ]]; then
    read -r -a ARGS <<< "$SSH_ORIGINAL_COMMAND"
    [[ "${ARGS[0]:-}" == "desplegar" ]] && ARGS=("${ARGS[@]:1}")
    set -- "${ARGS[@]}"
fi

AMBIENTE="${1:-}"
IMAGEN="${2:-}"
RESETDB="${3:-}"

uso() { echo "Uso: desplegar.sh <testing|produccion> <imagen ghcr.io/...:etiqueta> [--resetdb]" >&2; exit 2; }
[[ "$AMBIENTE" == "testing" || "$AMBIENTE" == "produccion" ]] || uso
[[ "$IMAGEN" =~ ^ghcr\.io/[a-z0-9._/-]+(:[A-Za-z0-9._-]+|@sha256:[a-f0-9]{64})$ ]] || uso
[[ -z "$RESETDB" || "$RESETDB" == "--resetdb" ]] || uso

# Solo se aceptan imágenes del repositorio del proyecto (lo guarda preparar.sh).
if [[ -f "$BASE/repositorio" ]]; then
    PERMITIDO="$(tr -d '[:space:]' < "$BASE/repositorio")"
    if [[ "$IMAGEN" != "$PERMITIDO:"* && "$IMAGEN" != "$PERMITIDO@"* ]]; then
        echo "ERROR: solo se despliegan imágenes de $PERMITIDO" >&2
        exit 2
    fi
fi

DIR="$BASE/$AMBIENTE"
ENV_FILE="$DIR/.env"
[[ -f "$ENV_FILE" ]] || { echo "No existe $ENV_FILE: correr antes preparar.sh" >&2; exit 1; }
cd "$DIR"

dc() { docker compose -p "simulador-$AMBIENTE" -f "$DIR/compose.yaml" --env-file "$ENV_FILE" --project-directory "$DIR" "$@"; }
registrar() { echo "$(date '+%F %T') $AMBIENTE $*" >> "$BASE/despliegues.log"; }

# 1) Bajar la imagen (con el token, si vino uno).
if [[ ! -t 0 ]]; then
    TOKEN="$(cat || true)"
    if [[ -n "$TOKEN" ]]; then
        echo "$TOKEN" | docker login ghcr.io -u despliegue --password-stdin >/dev/null 2>&1 \
            || echo "    Aviso: no se pudo iniciar sesión en ghcr.io (si la imagen es pública, no hace falta)."
    fi
fi
echo "==> Bajando $IMAGEN"
if ! docker pull -q "$IMAGEN"; then
    # Las etiquetas llevan el commit (sha-xxxxxxx): si ya está en el servidor, es la misma imagen.
    if docker image inspect "$IMAGEN" >/dev/null 2>&1; then
        echo "    Aviso: no se pudo bajar; se usa la copia que ya está en el servidor."
    else
        echo "ERROR: no se pudo bajar $IMAGEN" >&2
        exit 1
    fi
fi
docker logout ghcr.io >/dev/null 2>&1 || true

# 2) Sacar de la imagen el compose.yaml y la huella del esquema.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
CONTENEDOR="$(docker create "$IMAGEN")"
docker cp "$CONTENEDOR:/app/deploy/compose.yaml" "$TMP/compose.yaml"
docker cp "$CONTENEDOR:/app/esquema.txt" "$TMP/esquema.txt"
docker rm "$CONTENEDOR" >/dev/null
ESQUEMA_NUEVO="$(tr -d '[:space:]' < "$TMP/esquema.txt")"
ESQUEMA_ACTUAL=""
[[ -f "$DIR/esquema.txt" ]] && ESQUEMA_ACTUAL="$(tr -d '[:space:]' < "$DIR/esquema.txt")"
IMAGEN_ANTERIOR="$(grep -E '^IMAGEN=' "$ENV_FILE" | cut -d= -f2- || true)"

# 3) ¿Hay que recrear la base?
RECREAR=no
if [[ -z "$ESQUEMA_ACTUAL" ]]; then
    echo "==> Primer despliegue en $AMBIENTE: se crean las tablas"
    RECREAR=si
elif [[ "$ESQUEMA_NUEVO" != "$ESQUEMA_ACTUAL" ]]; then
    if [[ "$AMBIENTE" == "testing" || "$RESETDB" == "--resetdb" ]]; then
        echo "==> Cambió el esquema de la base ($ESQUEMA_ACTUAL -> $ESQUEMA_NUEVO): se recrea"
        RECREAR=si
    else
        echo "ERROR: esta versión cambia el esquema de la base ($ESQUEMA_ACTUAL -> $ESQUEMA_NUEVO)." >&2
        echo "Desplegarla en producción BORRA las sesiones. Descarguen los datos y usen el" >&2
        echo "workflow 'Recrear base' (o este script con --resetdb). No se cambió nada." >&2
        registrar "RECHAZADO (cambio de esquema) $IMAGEN"
        exit 3
    fi
elif [[ "$RESETDB" == "--resetdb" ]]; then
    echo "==> Se pidió recrear la base"
    RECREAR=si
fi

# 4) Instalar el compose nuevo y apuntar el .env a la imagen nueva.
cp "$TMP/compose.yaml" "$DIR/compose.yaml"
mkdir -p "$DIR/respaldos"
if grep -qE '^IMAGEN=' "$ENV_FILE"; then
    sed -i "s|^IMAGEN=.*|IMAGEN=$IMAGEN|" "$ENV_FILE"
else
    echo "IMAGEN=$IMAGEN" >> "$ENV_FILE"
fi

if [[ "$RECREAR" == "si" ]]; then
    # --wait: esperar a que PostgreSQL acepte conexiones (healthcheck) antes de seguir.
    dc up -d --wait db
    if [[ -n "$ESQUEMA_ACTUAL" ]]; then
        ARCHIVO="$DIR/respaldos/antes-de-recrear-$(date +%Y%m%d-%H%M%S).sql.gz"
        echo "==> Respaldo previo: $ARCHIVO"
        dc exec -T db pg_dump -U otree otree | gzip > "$ARCHIVO"
    fi
    dc stop app >/dev/null 2>&1 || true
    dc run --rm --no-deps app otree resetdb --noinput
fi

# 5) Levantar y esperar a que responda.
echo "==> Levantando $AMBIENTE"
dc up -d --remove-orphans

esperar_salud() {
    local id estado
    for _ in $(seq 1 30); do
        id="$(dc ps -q app)"
        estado="$(docker inspect --format '{{.State.Health.Status}}' "$id" 2>/dev/null || echo desconocido)"
        [[ "$estado" == "healthy" ]] && return 0
        sleep 3
    done
    return 1
}

if esperar_salud; then
    echo "$ESQUEMA_NUEVO" > "$DIR/esquema.txt"
    registrar "OK $IMAGEN${RECREAR:+ (base recreada: $RECREAR)}"
    docker image prune -f >/dev/null
    echo "==> Listo: $AMBIENTE corre $IMAGEN"
    exit 0
fi

echo "ERROR: la nueva versión no responde. Últimas líneas del registro:" >&2
dc logs --tail 40 app >&2 || true
if [[ "$RECREAR" == "no" && -n "$IMAGEN_ANTERIOR" ]]; then
    echo "==> Volviendo a la versión anterior: $IMAGEN_ANTERIOR" >&2
    sed -i "s|^IMAGEN=.*|IMAGEN=$IMAGEN_ANTERIOR|" "$ENV_FILE"
    dc up -d --remove-orphans
    registrar "FALLÓ $IMAGEN; se volvió a $IMAGEN_ANTERIOR"
else
    registrar "FALLÓ $IMAGEN"
fi
exit 1
