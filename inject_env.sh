#!/bin/bash
# Script para inyectar variables de entorno en el HTML del HMI en tiempo de ejecución

# Buscar el HMI en múltiples ubicaciones posibles
# Priorizar /var/www/hmi porque es donde nginx sirve el HMI
HMI_INDEX=""
if [ -f "/var/www/hmi/index.html" ]; then
    HMI_INDEX="/var/www/hmi/index.html"
elif [ -f "/app/hmi/dist/index.html" ]; then
    HMI_INDEX="/app/hmi/dist/index.html"
elif [ -f "./hmi/dist/index.html" ]; then
    HMI_INDEX="./hmi/dist/index.html"
else
    # Buscar en la ubicación del paquete instalado
    HMI_INDEX=$(python3 -c "import pkg_resources; print(pkg_resources.resource_filename('automation', 'hmi/index.html'))" 2>/dev/null || echo "")
fi

TEMP_INDEX="/tmp/index.html.$$"

# Verificar que el archivo existe
if [ -z "$HMI_INDEX" ] || [ ! -f "$HMI_INDEX" ]; then
    echo "[WARNING] HMI index.html no encontrado en ubicaciones esperadas. Saltando inyección de variables."
    echo "[DEBUG] Buscado en: /app/hmi/dist/index.html, ./hmi/dist/index.html, /var/www/hmi/index.html"
    exit 0
fi

echo "[INFO] HMI encontrado en: $HMI_INDEX"

# Leer el contenido del HTML
CONTENT=$(cat "$HMI_INDEX")

# Verificar si ya existe window.__ENV__
if echo "$CONTENT" | grep -q "window.__ENV__"; then
    # Si ya existe, remover el script anterior
    CONTENT=$(echo "$CONTENT" | sed '/<script>window\.__ENV__/,/<\/script>/d')
fi

# Construir el script de inyección de variables
ENV_SCRIPT="<script>window.__ENV__ = window.__ENV__ || {};"

# Función para agregar variable al script
# Siempre agrega la variable (incluso si está vacía) para valores como "false"
add_var() {
    local var_name=$1
    local env_value="${2:-}"  # Usar valor vacío si no se proporciona
    
    # Escapar caracteres especiales para JavaScript (JSON escape)
    local escaped_value=$(printf '%s' "$env_value" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | sed "s/'/\\'/g" | sed 's/\$/\\$/g')
    ENV_SCRIPT="${ENV_SCRIPT} window.__ENV__.${var_name} = '${escaped_value}';"
}

# Construir VITE_API_HOST si no está definido, usando AUTOMATION_PORT
if [ -z "$VITE_API_HOST" ] && [ -n "$AUTOMATION_PORT" ]; then
    VITE_API_HOST="localhost:${AUTOMATION_PORT}"
elif [ -z "$VITE_API_HOST" ]; then
    # Fallback a puerto por defecto si AUTOMATION_PORT tampoco está definido
    VITE_API_HOST="localhost:8050"
fi

# Detectar automáticamente si se deben usar certificados SSL
# Si AUTOMATION_CERT_FILE y AUTOMATION_KEY_FILE están definidos y no están vacíos,
# establecer VITE_USE_HTTPS=true automáticamente si no está definido
if [ -z "$VITE_USE_HTTPS" ]; then
    if [ -n "$AUTOMATION_CERT_FILE" ] && [ -n "$AUTOMATION_KEY_FILE" ]; then
        # Verificar que los archivos existan (si son rutas completas o nombres de archivo)
        CERT_PATH=""
        KEY_PATH=""
        
        # Determinar la ruta del certificado
        # Remover comillas si las hay (por si vienen del .env con comillas)
        CERT_FILE_CLEAN=$(echo "$AUTOMATION_CERT_FILE" | sed "s/^[\"']//; s/[\"']$//")
        if [ -n "$CERT_FILE_CLEAN" ]; then
            if [ "${CERT_FILE_CLEAN#/}" != "$CERT_FILE_CLEAN" ]; then
                # Es una ruta absoluta
                CERT_PATH="$CERT_FILE_CLEAN"
            else
                # Es un nombre de archivo, buscar en /app/ssl/
                CERT_PATH="/app/ssl/$CERT_FILE_CLEAN"
            fi
        fi
        
        # Determinar la ruta de la clave
        # Remover comillas si las hay (por si vienen del .env con comillas)
        KEY_FILE_CLEAN=$(echo "$AUTOMATION_KEY_FILE" | sed "s/^[\"']//; s/[\"']$//")
        if [ -n "$KEY_FILE_CLEAN" ]; then
            if [ "${KEY_FILE_CLEAN#/}" != "$KEY_FILE_CLEAN" ]; then
                # Es una ruta absoluta
                KEY_PATH="$KEY_FILE_CLEAN"
            else
                # Es un nombre de archivo, buscar en /app/ssl/
                KEY_PATH="/app/ssl/$KEY_FILE_CLEAN"
            fi
        fi
        
        # Si ambos archivos existen, usar HTTPS
        if [ -f "$CERT_PATH" ] && [ -f "$KEY_PATH" ]; then
            VITE_USE_HTTPS="true"
            echo "[INFO] Certificados SSL detectados en $CERT_PATH y $KEY_PATH"
            echo "[INFO] Configurando VITE_USE_HTTPS=true"
        else
            VITE_USE_HTTPS="false"
            echo "[WARNING] Certificados SSL no encontrados:"
            echo "[DEBUG] CERT_PATH=$CERT_PATH (existe: $([ -f "$CERT_PATH" ] && echo 'sí' || echo 'no'))"
            echo "[DEBUG] KEY_PATH=$KEY_PATH (existe: $([ -f "$KEY_PATH" ] && echo 'sí' || echo 'no'))"
            echo "[INFO] Configurando VITE_USE_HTTPS=false"
        fi
    else
        VITE_USE_HTTPS="false"
        echo "[INFO] Certificados SSL no configurados, configurando VITE_USE_HTTPS=false"
    fi
fi

# Asegurar que VITE_USE_HTTPS siempre tenga un valor
if [ -z "$VITE_USE_HTTPS" ]; then
    VITE_USE_HTTPS="false"
fi

# Agregar variables de entorno
# VITE_USE_HTTPS siempre se inyecta (true o false) para que el frontend sepa qué usar
if [ -n "$VITE_API_BASE_URL" ]; then
    add_var "VITE_API_BASE_URL" "$VITE_API_BASE_URL"
fi

# Siempre inyectar VITE_USE_HTTPS (incluso si es false)
add_var "VITE_USE_HTTPS" "$VITE_USE_HTTPS"

if [ -n "$VITE_API_HOST" ]; then
    add_var "VITE_API_HOST" "$VITE_API_HOST"
fi

if [ -n "$VITE_SOCKET_IO_URL" ]; then
    add_var "VITE_SOCKET_IO_URL" "$VITE_SOCKET_IO_URL"
fi

# Log de las variables que se inyectarán
echo "[DEBUG] Variables a inyectar en $HMI_INDEX:"
echo "[DEBUG]   VITE_USE_HTTPS='$VITE_USE_HTTPS'"
echo "[DEBUG]   VITE_API_HOST='$VITE_API_HOST'"
echo "[DEBUG]   VITE_API_BASE_URL='$VITE_API_BASE_URL'"
echo "[DEBUG]   VITE_SOCKET_IO_URL='$VITE_SOCKET_IO_URL'"

ENV_SCRIPT="${ENV_SCRIPT}</script>"

# Inyectar el script antes del cierre de </head> o </body>
# Manejar HTML minificado (una sola línea) y HTML normal (múltiples líneas)
# Usar awk para mejor manejo de HTML minificado y caracteres especiales
# Escribir el script a un archivo temporal para evitar problemas de escape
echo "$ENV_SCRIPT" > "$TEMP_INDEX.env"
ENV_SCRIPT_CONTENT=$(cat "$TEMP_INDEX.env")

# Intentar diferentes métodos de inyección según la estructura del HTML
if echo "$CONTENT" | grep -q "</head>"; then
    # HTML tiene </head>, inyectar antes de él
    CONTENT=$(echo "$CONTENT" | awk -v script="$ENV_SCRIPT_CONTENT" '{gsub("</head>", script "</head>"); print}')
elif echo "$CONTENT" | grep -q "</body>"; then
    # HTML tiene </body> pero no </head>, inyectar antes de </body>
    CONTENT=$(echo "$CONTENT" | awk -v script="$ENV_SCRIPT_CONTENT" '{gsub("</body>", script "</body>"); print}')
elif echo "$CONTENT" | grep -q "<head"; then
    # HTML tiene <head> pero no </head>, inyectar después de <head...>
    # Usar sed con escape adecuado
    CONTENT=$(echo "$CONTENT" | sed "s|<head[^>]*>|&${ENV_SCRIPT_CONTENT}|")
elif echo "$CONTENT" | grep -q "<html"; then
    # Si no hay <head>, inyectar después de <html>
    CONTENT=$(echo "$CONTENT" | sed "s|<html[^>]*>|&${ENV_SCRIPT_CONTENT}|")
else
    # Último recurso: agregar al principio del contenido
    CONTENT="${ENV_SCRIPT_CONTENT}${CONTENT}"
fi

# Limpiar archivo temporal
rm -f "$TEMP_INDEX.env"

# Escribir el contenido modificado de forma segura
echo "$CONTENT" > "$TEMP_INDEX"
if [ $? -eq 0 ]; then
    mv "$TEMP_INDEX" "$HMI_INDEX"
    echo "[INFO] Variables de entorno inyectadas exitosamente en $HMI_INDEX"
    
    # Verificar que las variables se inyectaron correctamente
    if grep -q "window.__ENV__" "$HMI_INDEX"; then
        echo "[INFO] Verificación: window.__ENV__ encontrado en el HTML"
        # Mostrar el contenido inyectado para depuración (primeros 200 caracteres)
        # Usar perl o sed para extraer el contenido entre window.__ENV__ y </script>
        ENV_CONTENT=$(grep -o "window\.__ENV__[^<]*</script>" "$HMI_INDEX" 2>/dev/null | head -1)
        if [ -z "$ENV_CONTENT" ]; then
            # Si no se encuentra con </script>, buscar solo window.__ENV__
            ENV_CONTENT=$(grep -o "window\.__ENV__[^<]*" "$HMI_INDEX" 2>/dev/null | head -1)
        fi
        if [ -n "$ENV_CONTENT" ]; then
            echo "[DEBUG] Contenido inyectado: ${ENV_CONTENT:0:200}..."
        else
            echo "[DEBUG] window.__ENV__ encontrado pero no se pudo extraer el contenido completo"
        fi
    else
        echo "[WARNING] window.__ENV__ no se encontró en el HTML después de la inyección"
        echo "[DEBUG] Verificando contenido del archivo (primeros 500 caracteres)..."
        head -c 500 "$HMI_INDEX" | tail -c 200
        echo ""
    fi
else
    echo "[ERROR] No se pudo escribir el archivo temporal"
    rm -f "$TEMP_INDEX"
    exit 1
fi

