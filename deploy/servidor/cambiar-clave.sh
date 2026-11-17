#!/usr/bin/env bash
#
# Cambia la contraseña de administración (la del docente) de un ambiente.
#
# Uso (como root, en el servidor):
#     bash /tmp/simulador/deploy/servidor/cambiar-clave.sh testing
#     bash /tmp/simulador/deploy/servidor/cambiar-clave.sh produccion
#
# La contraseña se pide al correr el script (no va en el comando, para que no
# quede en el historial del servidor). Es la del usuario "admin" de oTree, que
# sirve para el panel de oTree y para el tablero docente (que usa el mismo login).
# Se guarda en OTREE_ADMIN_PASSWORD de <ambiente>/.env y se reinicia la app del
# ambiente para que la tome. Las sesiones y los datos no se tocan; quien tenga la
# sesión iniciada tendrá que volver a ingresar.
#
set -euo pipefail

BASE=/opt/simulador
AMBIENTE="${1:-}"

if [[ $EUID -ne 0 ]]; then echo "Ejecutar como root (sudo bash cambiar-clave.sh <ambiente>)"; exit 1; fi
if [[ "$AMBIENTE" != "testing" && "$AMBIENTE" != "produccion" ]]; then
    echo "Uso: bash cambiar-clave.sh <testing|produccion>"; exit 2
fi

ENV_AMB="$BASE/$AMBIENTE/.env"
[[ -f "$ENV_AMB" ]] || { echo "No existe $ENV_AMB: el servidor no está preparado (correr preparar.sh)."; exit 1; }

# Mismas reglas que preparar.sh: los caracteres prohibidos rompen el archivo de configuración.
while true; do
    read -rsp "Nueva contraseña de administración de $AMBIENTE: " CLAVE; echo
    read -rsp "Repetirla: " CLAVE2; echo
    if [[ -z "$CLAVE" || "$CLAVE" != "$CLAVE2" ]]; then
        echo "No coinciden o está vacía."
    elif [[ ${#CLAVE} -lt 10 ]]; then
        echo "Usá al menos 10 caracteres."
    elif [[ "$CLAVE" =~ [[:space:]\"\'\$\\\`] ]]; then
        echo "Evitá espacios, comillas, \$, \\ y \` (rompen el archivo de configuración)."
    else
        break
    fi
done
unset CLAVE2

echo "==> Guardando la contraseña"
# Respaldo por si algo sale mal.
RESPALDO="$ENV_AMB.antes-$(date +%Y%m%d-%H%M%S)"
cp -p "$ENV_AMB" "$RESPALDO"
if grep -qE '^OTREE_ADMIN_PASSWORD=' "$ENV_AMB"; then
    # Reemplazo sin sed (la contraseña puede tener caracteres que sed interpretaría).
    awk -v c="$CLAVE" 'BEGIN{FS=OFS="="} /^OTREE_ADMIN_PASSWORD=/{print "OTREE_ADMIN_PASSWORD", c; next} {print}' \
        "$ENV_AMB" > "$ENV_AMB.nuevo"
else
    { cat "$ENV_AMB"; echo "OTREE_ADMIN_PASSWORD=$CLAVE"; } > "$ENV_AMB.nuevo"
fi
unset CLAVE
cat "$ENV_AMB.nuevo" > "$ENV_AMB" && rm -f "$ENV_AMB.nuevo"   # conserva dueño y permisos

echo "==> Reiniciando la app de $AMBIENTE"
if [[ -f "$BASE/$AMBIENTE/compose.yaml" ]]; then
    docker compose -p "simulador-$AMBIENTE" -f "$BASE/$AMBIENTE/compose.yaml" --env-file "$ENV_AMB" \
        --project-directory "$BASE/$AMBIENTE" up -d --no-deps --force-recreate app
else
    echo "    $AMBIENTE todavía no fue desplegado: la contraseña se aplica en el primer despliegue."
fi

echo
echo "Listo. Usuario: admin · contraseña: la que acabás de escribir."
echo "Respaldo de la configuración anterior: $RESPALDO (si todo funciona, se puede borrar)."
