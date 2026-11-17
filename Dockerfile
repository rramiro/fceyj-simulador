# Imagen del simulador (oTree en modo producción).
# La construye GitHub Actions y la publica en ghcr.io; ver DESPLIEGUE.md.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OTREE_PRODUCTION=1 \
    # Confiar en los encabezados X-Forwarded-* del proxy (Caddy), para que oTree arme
    # las direcciones con https. El contenedor solo es accesible desde la red interna de Docker.
    FORWARDED_ALLOW_IPS=*

WORKDIR /app

# Dependencias primero, para aprovechar la caché de capas.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Huella del esquema de la base: el despliegue la compara con la del servidor
# para saber si hace falta recrear la base (oTree no tiene migraciones).
ARG VERSION=desarrollo
RUN python scripts/esquema.py --huella > /app/esquema.txt \
    && echo "$VERSION" > /app/version.txt \
    && useradd --uid 1000 --no-create-home --home-dir /app --shell /usr/sbin/nologin otree \
    && chown -R otree /app
USER otree

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/static/portada/index.html', timeout=4)"

# prodserver lanza un proceso auxiliar con el comando "otree", que está en el PATH de la imagen.
CMD ["otree", "prodserver", "0.0.0.0:8000"]
