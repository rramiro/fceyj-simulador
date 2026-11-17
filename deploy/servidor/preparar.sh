#!/usr/bin/env bash
#
# Prepara un servidor Ubuntu 24.04 para los dos ambientes del simulador.
# Se corre una sola vez (o de nuevo para actualizar el proxy o desplegar.sh;
# no pisa la configuración existente).
#
# Uso (como root, en el servidor, desde una copia del repositorio):
#     git clone https://github.com/rramiro/fceyj-simulador.git /tmp/simulador
#     bash /tmp/simulador/deploy/servidor/preparar.sh
#
# Pide: dominios de producción y testing, correo para HTTPS y las contraseñas
# de administración de cada ambiente. Al final muestra lo que hay que cargar
# en GitHub (Settings → Secrets and variables → Actions).
#
set -euo pipefail

ORIGEN="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # carpeta deploy/ del repositorio
BASE=/opt/simulador
USUARIO=despliegue

# Dominios de la Facultad (se ofrecen por defecto; se pueden cambiar al correr el script).
DOMINIO_PRODUCCION_DEFECTO=simulador.eco.unlpam.edu.ar
DOMINIO_TESTING_DEFECTO=test.simulador.eco.unlpam.edu.ar

if [[ $EUID -ne 0 ]]; then echo "Ejecutar como root (sudo bash preparar.sh)"; exit 1; fi

pedir_clave() {   # pedir_clave <variable> <descripción>
    local clave clave2
    while true; do
        read -rsp "    Contraseña de administración de $2: " clave; echo
        read -rsp "    Repetirla: " clave2; echo
        if [[ -z "$clave" || "$clave" != "$clave2" ]]; then
            echo "    No coinciden o está vacía."
        elif [[ ${#clave} -lt 10 ]]; then
            echo "    Usá al menos 10 caracteres."
        elif [[ "$clave" =~ [[:space:]\"\'\$\\\`] ]]; then
            echo "    Evitá espacios, comillas, \$, \\ y \` (rompen el archivo de configuración)."
        else
            printf -v "$1" '%s' "$clave"
            return
        fi
    done
}

echo "==> 1/6 Docker y firewall"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q docker.io docker-compose-v2 ufw openssl
systemctl enable --now docker
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443 >/dev/null
ufw --force enable >/dev/null

echo "==> 2/6 Carpetas y script de despliegue"
mkdir -p "$BASE"/{bin,proxy,testing,produccion}
install -m 755 "$ORIGEN/servidor/desplegar.sh" "$BASE/bin/desplegar.sh"
# Imagen permitida: ghcr.io/<dueño>/<repositorio>, tomada del repositorio clonado.
URL_REPO="$(git -C "$ORIGEN/.." remote get-url origin 2>/dev/null || echo https://github.com/rramiro/fceyj-simulador.git)"
IMAGEN_PERMITIDA="ghcr.io/$(echo "$URL_REPO" | sed -E 's#^.*github\.com[:/]##; s#\.git$##' | tr '[:upper:]' '[:lower:]')"
echo "$IMAGEN_PERMITIDA" > "$BASE/repositorio"
echo "    Se aceptan imágenes de: $IMAGEN_PERMITIDA"
cp "$ORIGEN/proxy/compose.yaml" "$ORIGEN/proxy/Caddyfile" "$BASE/proxy/"
docker network inspect web >/dev/null 2>&1 || docker network create web >/dev/null

echo "==> 3/6 Dominios del proxy"
if [[ -f "$BASE/proxy/.env" ]]; then
    echo "    Ya configurado ($BASE/proxy/.env); se conserva."
else
    read -rp "    Dominio de producción [$DOMINIO_PRODUCCION_DEFECTO]: " DOM_PROD
    read -rp "    Dominio de testing    [$DOMINIO_TESTING_DEFECTO]: " DOM_TEST
    DOM_PROD="${DOM_PROD:-$DOMINIO_PRODUCCION_DEFECTO}"
    DOM_TEST="${DOM_TEST:-$DOMINIO_TESTING_DEFECTO}"
    read -rp "    Correo para avisos de los certificados: " CORREO
    umask 077
    printf 'DOMINIO_PRODUCCION=%s\nDOMINIO_TESTING=%s\nCORREO=%s\n' "$DOM_PROD" "$DOM_TEST" "$CORREO" > "$BASE/proxy/.env"
    umask 022
fi
chmod 600 "$BASE/proxy/.env"

valor() {   # valor <archivo .env> <variable>
    grep -E "^$2=" "$1" 2>/dev/null | head -1 | cut -d= -f2- | sed -E "s/^'(.*)'$/\1/"
}

echo "==> 4/6 Configuración de cada ambiente"
for AMB in testing produccion; do
    ENV_AMB="$BASE/$AMB/.env"
    if [[ -f "$ENV_AMB" ]]; then
        echo "    $AMB: ya configurado; se conserva."
    else
        pedir_clave CLAVE "$AMB"
        umask 077
        cat > "$ENV_AMB" <<EOF
# Configuración secreta del ambiente $AMB. No subir a ningún repositorio.
AMBIENTE=$AMB
POSTGRES_PASSWORD=$(openssl rand -hex 16)
OTREE_ADMIN_PASSWORD=$CLAVE
OTREE_SECRET_KEY=$(openssl rand -hex 32)
OTREE_AUTH_LEVEL=STUDY
RESPALDOS_DIAS=14
EOF
        umask 022
        unset CLAVE
    fi

    # Tablero docente: clave REST de oTree (en el ambiente y en el proxy) y la contraseña
    # de administración en bcrypt para el proxy. Se completan si faltan (servidores viejos).
    SUFIJO="$(echo "$AMB" | tr '[:lower:]' '[:upper:]')"
    if [[ -z "$(valor "$ENV_AMB" OTREE_REST_KEY)" ]]; then
        echo "OTREE_REST_KEY=$(openssl rand -hex 24)" >> "$ENV_AMB"
    fi
    CLAVE_REST="$(valor "$ENV_AMB" OTREE_REST_KEY)"
    sed -i "/^REST_KEY_$SUFIJO=/d" "$BASE/proxy/.env"
    echo "REST_KEY_$SUFIJO=$CLAVE_REST" >> "$BASE/proxy/.env"
    if [[ -z "$(valor "$BASE/proxy/.env" "DOCENTE_HASH_$SUFIJO")" ]]; then
        HASH="$(docker run --rm caddy:2.8-alpine caddy hash-password --plaintext "$(valor "$ENV_AMB" OTREE_ADMIN_PASSWORD)")"
        # Entre comillas simples: el hash tiene "$" y docker compose no debe interpretarlos.
        echo "DOCENTE_HASH_$SUFIJO='$HASH'" >> "$BASE/proxy/.env"
    fi
    unset CLAVE_REST HASH
done

echo "    Levantando el proxy"
docker compose -p simulador-proxy -f "$BASE/proxy/compose.yaml" --env-file "$BASE/proxy/.env" \
    --project-directory "$BASE/proxy" up -d --force-recreate

echo "==> 5/6 Usuario de despliegue para GitHub Actions"
if ! id -u "$USUARIO" &>/dev/null; then
    useradd --create-home --shell /bin/bash "$USUARIO"
fi
usermod -aG docker "$USUARIO"
chown -R "$USUARIO:$USUARIO" "$BASE/testing" "$BASE/produccion"
touch "$BASE/despliegues.log" && chown "$USUARIO:$USUARIO" "$BASE/despliegues.log"

SSH_DIR="/home/$USUARIO/.ssh"
mkdir -p "$SSH_DIR" && chmod 700 "$SSH_DIR"
CLAVE_PRIVADA=""
if [[ ! -s "$SSH_DIR/authorized_keys" ]]; then
    TMPK="$(mktemp -d)"
    ssh-keygen -q -t ed25519 -N "" -C "github-actions-simulador" -f "$TMPK/id"
    # La clave solo puede ejecutar desplegar.sh: sin consola, sin túneles, sin copiar archivos.
    echo "command=\"$BASE/bin/desplegar.sh\",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty $(cat "$TMPK/id.pub")" \
        > "$SSH_DIR/authorized_keys"
    CLAVE_PRIVADA="$(cat "$TMPK/id")"
    rm -rf "$TMPK"
fi
chmod 600 "$SSH_DIR/authorized_keys"
chown -R "$USUARIO:$USUARIO" "$SSH_DIR"

echo "==> 6/6 Datos para GitHub"
IP_DEFECTO="$(hostname -I | awk '{print $1}')"
read -rp "    IP o nombre con que GitHub se conecta por SSH [$IP_DEFECTO]: " HOST
HOST="${HOST:-$IP_DEFECTO}"

echo
echo "================================================================================"
echo " Cargar en GitHub → Settings → Secrets and variables → Actions → Secrets:"
echo "================================================================================"
echo
echo "SSH_HOST:"
echo "$HOST"
echo
echo "SSH_KNOWN_HOSTS:"
echo "$HOST $(cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub)"
echo
if [[ -n "$CLAVE_PRIVADA" ]]; then
    echo "SSH_KEY (copiar las líneas completas, incluidas BEGIN y END; no se vuelve a mostrar):"
    echo "$CLAVE_PRIVADA"
    unset CLAVE_PRIVADA
else
    echo "SSH_KEY: ya se había generado antes. Si se perdió, borrar"
    echo "  $SSH_DIR/authorized_keys y volver a correr este script."
fi
echo
echo "================================================================================"
echo "Listo. El primer despliegue lo hace GitHub Actions (ver DESPLIEGUE.md)."
