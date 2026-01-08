#!/bin/bash
# Script para construir el paquete PyAutomationIO incluyendo el HMI

set -e

echo "=========================================="
echo "Construyendo paquete PyAutomationIO"
echo "=========================================="

# Verificar que estamos en el directorio correcto
if [ ! -f "setup.py" ]; then
    echo "Error: setup.py no encontrado. Ejecuta este script desde el directorio raíz del proyecto."
    exit 1
fi

# Construir el HMI si no existe o si se solicita reconstrucción
if [ ! -d "hmi/dist" ] || [ "$1" == "--rebuild-hmi" ]; then
    echo ""
    echo "Construyendo HMI..."
    if [ ! -d "hmi" ]; then
        echo "Error: Directorio hmi/ no encontrado."
        exit 1
    fi
    
    cd hmi
    
    # Verificar que package.json existe
    if [ ! -f "package.json" ]; then
        echo "Error: package.json no encontrado en hmi/"
        exit 1
    fi
    
    # Instalar dependencias si node_modules no existe
    if [ ! -d "node_modules" ]; then
        echo "Instalando dependencias de npm..."
        npm install
    fi
    
    # Construir el HMI
    echo "Compilando HMI para producción..."
    npm run build
    
    cd ..
    echo "HMI construido exitosamente."
else
    echo "HMI ya está construido. Usa --rebuild-hmi para reconstruirlo."
fi

# Limpiar builds anteriores
echo ""
echo "Limpiando builds anteriores..."
rm -rf build/ dist/ *.egg-info/
rm -rf automation/hmi/

# Construir el paquete
echo ""
echo "Construyendo el paquete Python..."
python3 setup.py sdist bdist_wheel

echo ""
echo "=========================================="
echo "Paquete construido exitosamente!"
echo "Archivos generados en: dist/"
echo "=========================================="

