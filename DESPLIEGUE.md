# Despliegue con Docker y GitHub Actions

El simulador corre en contenedores Docker en un servidor propio (VPS), con **dos ambientes**:

| Ambiente | Para qué | Se actualiza |
|---|---|---|
| **testing** (`testing.simulador.<dominio>`) | Probar los cambios antes de usarlos en clase | Automáticamente con cada push a `main` |
| **produccion** (`simulador.<dominio>`) | Las clases | Después de testing, **con aprobación manual** en GitHub |

```
push a main ─► Pruebas (bots + modelo) ─► Imagen Docker (ghcr.io) ─► testing ─► [aprobación] ─► producción
```

A producción va **exactamente la misma imagen** que se probó en testing.

## Cómo está armado

En el servidor, todo vive en `/opt/simulador/`:

```
/opt/simulador/
├── bin/desplegar.sh        script que ejecuta GitHub Actions (y que se puede correr a mano)
├── proxy/                  Caddy: HTTPS automático y reparto por dominio (puertos 80 y 443)
├── testing/                compose.yaml + .env + respaldos/ del ambiente testing
├── produccion/             compose.yaml + .env + respaldos/ del ambiente produccion
└── despliegues.log         historial de despliegues
```

Cada ambiente tiene tres contenedores: **app** (oTree), **db** (PostgreSQL, con su propio volumen)
y **respaldo** (un `pg_dump` diario en `respaldos/`, se guardan 14 días).

Archivos del repositorio:

| Archivo | Qué hace |
|---|---|
| `Dockerfile` | Imagen de oTree en modo producción |
| `deploy/compose.yaml` | Servicios de un ambiente (viaja dentro de la imagen) |
| `deploy/proxy/` | Caddy y su configuración (la raíz `/` lleva a la portada) |
| `deploy/servidor/preparar.sh` | Prepara un servidor nuevo (una sola vez) |
| `deploy/servidor/desplegar.sh` | Despliega una imagen en un ambiente |
| `.github/workflows/ci.yml` | Pruebas en cada push y pull request |
| `.github/workflows/despliegue.yml` | Pruebas → imagen → testing → producción |
| `.github/workflows/recrear-base.yml` | Recrea la base de un ambiente (borra sus sesiones) |
| `scripts/esquema.py` | Huella de los campos del modelo (ver *Cambios en el modelo*) |

---

## Puesta en marcha (una sola vez)

### 1. Servidor

Crear un VPS con **Ubuntu 24.04**, **2 GB de RAM** (unos 12 USD por mes; alcanza para los dos
ambientes) y acceso con clave SSH. Anotar la IP.

### 2. Dominios

Crear dos registros DNS tipo **A** apuntando a la IP del servidor, por ejemplo:

- `simulador.eco.unlpam.edu.ar` → producción
- `testing.simulador.eco.unlpam.edu.ar` → testing

(Si son subdominios de la Facultad, los crea el área de sistemas.)

### 3. Preparar el servidor

```
ssh root@<ip>
apt-get update && apt-get install -y git
git clone https://github.com/rramiro/fceyj-simulador.git /tmp/simulador
bash /tmp/simulador/deploy/servidor/preparar.sh
```

El script instala Docker y el firewall, levanta el proxy y pide:

- los dos dominios y un correo (para los avisos de los certificados HTTPS);
- la **contraseña de administración** de cada ambiente (la que usan los docentes en el panel;
  al menos 10 caracteres, sin espacios, comillas, `$`, `\` ni `` ` ``).

Crea también el usuario `despliegue`, con una clave SSH que **solo puede ejecutar
`desplegar.sh`** (no abre una consola ni copia archivos), y al final muestra tres datos.

### 4. Configurar GitHub

En el repositorio → **Settings**:

1. **Secrets and variables → Actions → Secrets** → cargar los tres datos que mostró el script:
   `SSH_HOST`, `SSH_KNOWN_HOSTS` y `SSH_KEY`.
2. **Secrets and variables → Actions → Variables** → crear:
   - `DESPLIEGUE_ACTIVO` = `true` (mientras no exista, los push a `main` solo corren las pruebas);
   - `DOMINIO_TESTING` y `DOMINIO_PRODUCCION` (opcionales: muestran el enlace en cada despliegue).
3. **Environments** → crear `testing` (sin reglas) y `produccion` con
   **Required reviewers** = quien aprueba los pases a producción.

### 5. Primer despliegue

**Actions → Despliegue → Run workflow**. Se despliega testing; después GitHub pide aprobar
producción (**Review deployments → Approve**). En el primer despliegue se crean las tablas.

Probar en `https://testing.simulador.<dominio>/` y `https://simulador.<dominio>/`.

---

## Uso diario

- **Cambiar el simulador:** push a `main` (o merge de un pull request). Se prueba, se despliega en
  testing y queda esperando la aprobación para producción.
- **No aprobar producción durante una clase:** el reinicio corta unos segundos las páginas de
  espera (se reconectan solas, pero mejor evitarlo).
- **Volver a una versión anterior:** en **Actions → Despliegue**, abrir una ejecución anterior que
  haya funcionado y **Re-run all jobs**; o en el servidor:
  `sudo -u despliegue /opt/simulador/bin/desplegar.sh produccion ghcr.io/rramiro/fceyj-simulador:sha-<commit>`.
- **Si la versión nueva no arranca**, `desplegar.sh` vuelve solo a la anterior y el workflow falla.

## Tablero docente

En `https://<dominio>/static/docente/` (también desde la portada: *Soy docente* → *Tablero docente*). Pide usuario
`admin` y la contraseña de administración del ambiente.

- Lista las sesiones del simulador (las partidas de *Demo* no aparecen: se abren por código).
- Para cada mercado muestra en qué trimestre y en qué pantalla está cada equipo, quién está
  demorando al mercado, la participación, el resultado acumulado y el puesto. Se actualiza solo
  cada 10 segundos.
- Al elegir un equipo: su historial trimestre a trimestre, la **devolución automática**
  (reglas en `comercializacion/devolucion.py`) y un cuadro para el **comentario del docente**.
  El equipo ve la devolución y el comentario en su pantalla de resultado final.

Cómo funciona: el juego guarda el estado de cada equipo en `participant.vars['tablero']` y el
tablero lo lee con la API REST de oTree. En el servidor, Caddy protege `/static/docente/` y `/api/`
con la contraseña y agrega la clave REST (`OTREE_REST_KEY`) que exige oTree; la clave nunca llega
al navegador. `preparar.sh` genera la clave y guarda la contraseña cifrada (bcrypt) en
`/opt/simulador/proxy/.env`. Si se cambia la contraseña de administración de un ambiente, borrar
la línea `DOCENTE_HASH_<AMBIENTE>` de ese archivo y volver a correr `preparar.sh`.

En la computadora (`otree devserver`) la API no pide clave: el tablero funciona directamente en
`http://localhost:8000/static/docente/index.html`.

## Cambios en el modelo (columnas de la base)

oTree **no tiene migraciones**: si cambian los campos de `Player`, `Group` o `Subsession`
(o la versión de oTree), hay que recrear la base, y eso **borra todas las sesiones**.

El despliegue lo detecta comparando la huella de `scripts/esquema.py`:

- **testing:** recrea la base sola (antes guarda un respaldo).
- **producción:** **se niega** a desplegar y el workflow falla con el aviso *Cambio de esquema*.
  Entonces:
  1. descargar los datos desde el panel (**Data**);
  2. **Actions → Recrear base → Run workflow**, ambiente `produccion`, escribir `BORRAR`;
  3. aprobar el despliegue.

  Antes de recrear se guarda un respaldo en `/opt/simulador/produccion/respaldos/`.

Conviene hacer estos cambios entre cuatrimestres.

## Respaldos

- Diarios, automáticos, en `/opt/simulador/<ambiente>/respaldos/diario-*.sql.gz` (14 días).
- Uno extra antes de cada recreación de la base (`antes-de-recrear-*.sql.gz`).
- Para restaurar uno en producción:

  ```
  cd /opt/simulador/produccion
  gunzip -c respaldos/<archivo>.sql.gz | docker compose -p simulador-produccion exec -T db psql -U otree otree
  ```

Conviene copiar periódicamente la carpeta de respaldos fuera del servidor.

## Problemas frecuentes

| Síntoma | Qué revisar (en el servidor) |
|---|---|
| El sitio no carga | `docker ps` (tienen que estar `caddy`, `app`, `db`); `docker logs simulador-proxy-caddy-1` |
| Error en un ambiente | `cd /opt/simulador/produccion && docker compose -p simulador-produccion logs --tail 50 app` |
| Falla "Conectar y desplegar" en Actions | Que los secretos `SSH_*` estén bien copiados (la clave completa, con BEGIN y END) |
| No sale el certificado HTTPS | Que los dominios ya apunten a la IP; después `docker restart simulador-proxy-caddy-1` |
| Olvidé la contraseña de administración | Editar `OTREE_ADMIN_PASSWORD` en `/opt/simulador/<ambiente>/.env`, borrar `DOCENTE_HASH_<AMBIENTE>` de `/opt/simulador/proxy/.env`, correr `preparar.sh` y desplegar de nuevo |
| Historial de despliegues | `cat /opt/simulador/despliegues.log` |

## Probar el stack en la computadora

Con Docker Desktop abierto, desde la carpeta del proyecto (PowerShell):

```
docker network create web
docker build -t simulador:local .
copy deploy\local\env.ejemplo deploy\local\.env
docker compose -p simulador-local -f deploy/compose.yaml -f deploy/local/compose.local.yaml --env-file deploy/local/.env --project-directory deploy/local up -d db
docker compose -p simulador-local -f deploy/compose.yaml -f deploy/local/compose.local.yaml --env-file deploy/local/.env --project-directory deploy/local run --rm app otree resetdb --noinput
docker compose -p simulador-local -f deploy/compose.yaml -f deploy/local/compose.local.yaml --env-file deploy/local/.env --project-directory deploy/local up -d
```

Queda en `http://localhost:8080/static/portada/index.html` (panel: usuario `admin`, contraseña
la del `.env`). Para bajarlo:
`docker compose -p simulador-local -f deploy/compose.yaml --env-file deploy/local/.env --project-directory deploy/local down -v`.
