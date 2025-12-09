# Etapa de construcción (Build Stage)
# Usamos python:3.11-slim-bookworm para coincidir con la versión de Python en distroless-debian12
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Instalar dependencias de compilación mínimas
# psycopg2-binary y numpy suelen tener wheels, pero build-essential asegura compilación si es necesario
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Instalamos las dependencias en un directorio específico (/install)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# Etapa de producción (Runtime Stage)
# Usamos Google Distroless para Python 3 (Debian 12)
FROM gcr.io/distroless/python3-debian12

WORKDIR /app

# Copiamos las dependencias instaladas desde la etapa de construcción
COPY --from=builder /install /usr/local

# Copiamos el código de la aplicación
COPY . .

# Establecemos variables de entorno
ENV PORT=8050
ENV OPCUA_SERVER_PORT=53530
# Aseguramos que Python encuentre los paquetes (aunque /usr/local suele estar en path)
ENV PYTHONPATH=/usr/local/lib/python3.11/site-packages

# Exponemos los puertos
EXPOSE ${PORT}
EXPOSE ${OPCUA_SERVER_PORT}

# Healthcheck usando script de Python (curl no existe en distroless)
HEALTHCHECK --interval=5s --timeout=10s --start-period=55s \
  CMD ["python", "/app/healthcheck.py"]

# Entrypoint usando script de Python (sh no existe en distroless estándar)
ENTRYPOINT ["python", "/app/entrypoint.py"]
