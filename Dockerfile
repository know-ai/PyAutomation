# ============================================================================
# Etapa 1: Construcción de dependencias Python
# ============================================================================
FROM python:3.11-slim-bookworm AS python-builder

WORKDIR /app

# Instalar dependencias de compilación mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Instalamos las dependencias en un directorio específico (/install)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================================
# Etapa 2: Construcción del frontend React
# ============================================================================
FROM node:20-slim AS frontend-builder

WORKDIR /app

# Copiar archivos de configuración del frontend
COPY hmi/package*.json ./hmi/

# Instalar dependencias del frontend
WORKDIR /app/hmi
RUN npm ci --only=production=false

# Copiar código fuente del frontend
COPY hmi/ .

# Construir el frontend para producción
# Configurar base path para servir en puerto independiente (sin prefijo)
ARG VITE_BASE_PATH=/
ENV VITE_BASE_PATH=${VITE_BASE_PATH}
RUN npm run build

# ============================================================================
# Etapa 3: Imagen final de producción
# ============================================================================
FROM python:3.11-slim-bookworm

WORKDIR /app

# Instalar nginx y supervisor para gestionar múltiples procesos
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Copiar dependencias Python desde la etapa de construcción
COPY --from=python-builder /install /usr/local

# Copiar código del backend
COPY . .

# Copiar el frontend construido desde la etapa de construcción
COPY --from=frontend-builder /app/hmi/dist /var/www/hmi

# Configurar nginx para servir el frontend
RUN cat > /etc/nginx/sites-available/hmi << 'EOF'
server {
    listen 3000;
    server_name _;
    root /var/www/hmi;
    index index.html;

    # Servir archivos estáticos
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache para assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Headers de seguridad
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
}
EOF
RUN ln -s /etc/nginx/sites-available/hmi /etc/nginx/sites-enabled/ && \
    rm -f /etc/nginx/sites-enabled/default

# Crear script wrapper para el backend que preserve las variables de entorno
RUN cat > /app/start-backend.sh << 'EOF'
#!/bin/bash
# Preservar variables de entorno del contenedor
export PORT=${PORT:-8050}
export OPCUA_SERVER_PORT=${OPCUA_SERVER_PORT:-53530}
export PYTHONPATH=${PYTHONPATH:-/usr/local/lib/python3.11/site-packages}
export PYTHONUNBUFFERED=${PYTHONUNBUFFERED:-1}
# Preservar otras variables de entorno importantes
export AUTOMATION_OPCUA_SERVER_PORT=${AUTOMATION_OPCUA_SERVER_PORT:-${OPCUA_SERVER_PORT}}
export AUTOMATION_APP_SECRET_KEY=${AUTOMATION_APP_SECRET_KEY}
export AUTOMATION_SUPERUSER_PASSWORD=${AUTOMATION_SUPERUSER_PASSWORD}
# Ejecutar el entrypoint
exec python /app/entrypoint.py
EOF
RUN chmod +x /app/start-backend.sh

# Configurar supervisor para gestionar nginx y el backend
RUN cat > /etc/supervisor/conf.d/supervisord.conf << 'EOF'
[supervisord]
nodaemon=true
user=root
logfile=/var/log/supervisor/supervisord.log
pidfile=/var/run/supervisord.pid

[program:nginx]
command=/usr/sbin/nginx -g "daemon off;"
autostart=true
autorestart=true
priority=10
stderr_logfile=/var/log/supervisor/nginx.err.log
stdout_logfile=/var/log/supervisor/nginx.out.log

[program:backend]
command=/app/start-backend.sh
directory=/app
autostart=true
autorestart=true
priority=20
startsecs=10
startretries=3
stderr_logfile=/var/log/supervisor/backend.err.log
stdout_logfile=/var/log/supervisor/backend.out.log
EOF

# Crear directorios de logs para supervisor
RUN mkdir -p /var/log/supervisor

# Establecemos variables de entorno
ENV PORT=8050
ENV HMI_PORT=3000
ENV OPCUA_SERVER_PORT=53530
ENV PYTHONPATH=/usr/local/lib/python3.11/site-packages
ENV PYTHONUNBUFFERED=1

# Exponemos los puertos
EXPOSE ${PORT}
EXPOSE ${HMI_PORT}
EXPOSE ${OPCUA_SERVER_PORT}

# Healthcheck (solo verifica el backend, nginx es más simple y no necesita verificación)
HEALTHCHECK --interval=10s --timeout=5s --start-period=90s --retries=3 \
  CMD python /app/healthcheck.py || exit 1

# Entrypoint usando supervisor para gestionar ambos servicios
ENTRYPOINT ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
