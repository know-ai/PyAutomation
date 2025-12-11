# Configuración del Sistema

Esta sección describe cómo exportar e importar la configuración del sistema PyAutomation.

## Exportar Configuración

La funcionalidad de exportación permite guardar toda la configuración del sistema en un archivo JSON. Esto es útil para:

- **Backup**: Crear copias de seguridad de la configuración
- **Migración**: Transferir configuración entre instancias
- **Versionado**: Mantener un historial de cambios de configuración
- **Replicación**: Duplicar configuración en múltiples sistemas

### ¿Qué se exporta?

La exportación incluye todas las tablas de **configuración** del sistema:

- **Manufacturer**: Fabricantes de dispositivos
- **Segment**: Segmentos de red/planta
- **Variables**: Variables físicas (presión, temperatura, etc.)
- **Units**: Unidades de medición
- **DataTypes**: Tipos de datos
- **Tags**: Etiquetas de proceso configuradas
- **AlarmTypes**: Tipos de alarmas
- **AlarmStates**: Estados de alarmas
- **Alarms**: Configuración de alarmas
- **Roles**: Roles de usuario
- **Users**: Usuarios del sistema
- **OPCUA**: Configuraciones de clientes OPC UA
- **AccessType**: Tipos de acceso OPC UA
- **OPCUAServer**: Configuraciones de servidores OPC UA
- **Machines**: Máquinas de estado
- **TagsMachines**: Relaciones entre tags y máquinas

### ¿Qué NO se exporta?

Los datos **históricos** no se incluyen en la exportación:

- **TagValue**: Valores históricos de tags
- **Events**: Eventos históricos
- **Logs**: Logs de operación
- **AlarmSummary**: Resúmenes históricos de alarmas

Estos datos se mantienen en la base de datos y no se afectan durante la importación.

### Exportar mediante API

#### Endpoint

```
GET /api/settings/export_config
```

#### Autenticación

Requiere token de autenticación en el header:

```
X-API-KEY: <tu_token>
```

#### Ejemplo con cURL

```bash
curl -X GET \
  http://localhost:5000/api/settings/export_config \
  -H "X-API-KEY: tu_token_aqui" \
  -o configuration_export.json
```

#### Ejemplo con Python

```python
import requests

url = "http://localhost:5000/api/settings/export_config"
headers = {"X-API-KEY": "tu_token_aqui"}

response = requests.get(url, headers=headers)

if response.status_code == 200:
    with open("configuration_export.json", "wb") as f:
        f.write(response.content)
    print("Configuración exportada exitosamente")
else:
    print(f"Error: {response.json()}")
```

#### Respuesta

**Éxito (200):**
- Archivo JSON descargable con nombre `configuration_export.json`

**Error (400):**
```json
{
  "message": "Database not connected"
}
```

**Error (401):**
```json
{
  "message": "Token is missing or invalid"
}
```

### Formato del Archivo Exportado

El archivo JSON exportado tiene la siguiente estructura:

```json
{
  "version": "1.0",
  "exported_at": "2024-01-15T10:30:00+00:00",
  "data": {
    "Manufacturer": [...],
    "Segment": [...],
    "Variables": [...],
    "Units": [...],
    "DataTypes": [...],
    "Tags": [...],
    "AlarmTypes": [...],
    "AlarmStates": [...],
    "Alarms": [...],
    "Roles": [...],
    "Users": [...],
    "OPCUA": [...],
    "AccessType": [...],
    "OPCUAServer": [...],
    "Machines": [...],
    "TagsMachines": [...]
  }
}
```

## Importar Configuración

La funcionalidad de importación permite restaurar la configuración del sistema desde un archivo JSON previamente exportado.

### Consideraciones Importantes

!!! warning "Advertencia"
    - La importación **no elimina** datos existentes, solo crea nuevos registros si no existen
    - Los registros duplicados (basados en nombres únicos) se **omiten** durante la importación
    - Los datos históricos (TagValue, Events, Logs, AlarmSummary) **no se afectan**
    - Las contraseñas de usuarios importados deben ser **restablecidas** después de la importación

### Orden de Importación

La importación se realiza en un orden específico para respetar las dependencias entre tablas:

1. Variables
2. Units (depende de Variables)
3. DataTypes
4. Manufacturer
5. Segment (depende de Manufacturer)
6. Tags (depende de Units, DataTypes, Segment)
7. AlarmTypes
8. AlarmStates
9. Alarms (depende de Tags, AlarmTypes, AlarmStates)
10. Roles
11. Users (depende de Roles)
12. OPCUA
13. AccessType
14. OPCUAServer (depende de AccessType)
15. Machines
16. TagsMachines (depende de Tags y Machines)

### Importar mediante API

#### Endpoint

```
POST /api/settings/import_config
```

#### Autenticación

Requiere token de autenticación en el header:

```
X-API-KEY: <tu_token>
```

#### Parámetros

- **file** (requerido): Archivo JSON con la configuración a importar

#### Ejemplo con cURL

```bash
curl -X POST \
  http://localhost:5000/api/settings/import_config \
  -H "X-API-KEY: tu_token_aqui" \
  -F "file=@configuration_export.json"
```

#### Ejemplo con Python

```python
import requests

url = "http://localhost:5000/api/settings/import_config"
headers = {"X-API-KEY": "tu_token_aqui"}

with open("configuration_export.json", "rb") as f:
    files = {"file": ("configuration_export.json", f, "application/json")}
    response = requests.post(url, headers=headers, files=files)

if response.status_code == 200:
    result = response.json()
    print(f"Importación exitosa: {result['message']}")
    print(f"Resumen: {result['summary']}")
else:
    print(f"Error: {response.json()}")
```

#### Respuesta

**Éxito (200):**
```json
{
  "message": "Configuration imported: 150 records imported, 10 skipped, 0 errors",
  "summary": {
    "imported": 150,
    "skipped": 10,
    "errors": 0
  },
  "results": {
    "imported": {
      "Variables": 5,
      "Units": 12,
      "Tags": 50,
      "Alarms": 20,
      ...
    },
    "skipped": {
      "Users": 2,
      "Roles": 1,
      ...
    },
    "errors": {}
  }
}
```

**Error (400):**
```json
{
  "message": "No file provided"
}
```

o

```json
{
  "message": "Invalid JSON file: Expecting value: line 1 column 1 (char 0)",
  "details": {
    "imported": {...},
    "skipped": {...},
    "errors": {...}
  }
}
```

**Error (401):**
```json
{
  "message": "Token is missing or invalid"
}
```

## Casos de Uso

### Backup y Restauración

1. **Exportar configuración actual:**
   ```bash
   curl -X GET http://localhost:5000/api/settings/export_config \
     -H "X-API-KEY: token" \
     -o backup_$(date +%Y%m%d).json
   ```

2. **Restaurar desde backup:**
   ```bash
   curl -X POST http://localhost:5000/api/settings/import_config \
     -H "X-API-KEY: token" \
     -F "file=@backup_20240115.json"
   ```

### Migración entre Sistemas

1. Exportar configuración del sistema origen
2. Importar en el sistema destino
3. Verificar que todos los registros se importaron correctamente
4. Restablecer contraseñas de usuarios

### Desarrollo y Testing

1. Exportar configuración de producción
2. Importar en ambiente de desarrollo/testing
3. Realizar pruebas sin afectar datos históricos
4. Restaurar configuración original si es necesario

## Mejores Prácticas

1. **Hacer backups regulares**: Exporta la configuración antes de realizar cambios importantes
2. **Verificar el archivo**: Revisa el JSON exportado antes de importarlo en otro sistema
3. **Probar en desarrollo**: Siempre prueba la importación en un ambiente de desarrollo primero
4. **Documentar cambios**: Mantén un registro de las exportaciones con fechas y descripciones
5. **Restablecer contraseñas**: Después de importar usuarios, restablece todas las contraseñas
6. **Validar dependencias**: Asegúrate de que todas las dependencias estén presentes antes de importar

## Solución de Problemas

### Error: "Database not connected"

- Verifica que la base de datos esté conectada
- Revisa la configuración de conexión

### Error: "Invalid JSON file"

- Verifica que el archivo sea un JSON válido
- Asegúrate de que el archivo no esté corrupto
- Revisa que el archivo sea del formato correcto (exportado desde este sistema)

### Registros no se importan

- Verifica que no existan registros con el mismo nombre (se omiten duplicados)
- Revisa los logs de errores en la respuesta
- Asegúrate de que todas las dependencias estén presentes

### Usuarios importados no pueden iniciar sesión

- Las contraseñas se establecen con valores por defecto durante la importación
- Debes restablecer las contraseñas usando el endpoint de cambio de contraseña

