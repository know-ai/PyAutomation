# Carga masiva de perfil geoespacial (LinearReferencingGeospatial)

Este proceso permite cargar el perfil geoespacial completo de un ducto para un segmento, usando archivos `CSV` o `XLSX`.

## Objetivo

Persistir puntos de referencia lineal (`KP`) con coordenadas geográficas para que los eventos (por ejemplo, fugas) puedan georreferenciarse e interpolarse correctamente.

## Endpoint de carga masiva

- `POST /linear-referencing-geospatial/bulk_import`
- Tipo de request: `multipart/form-data`

Campos del form-data:

- `file` (requerido): archivo `.csv` o `.xlsx`
- `segment_name` (opcional): segmento por defecto para filas que no lo incluyan
- `update_existing` (opcional, default `true`): si `true`, actualiza filas existentes con mismo `segment + kp`; si `false`, las omite

## Formato esperado del archivo

Columnas requeridas:

- `kp`
- `latitude`
- `longitude`

Columnas opcionales:

- `segment_name` (si no viene, se usa `segment_name` del form-data)
- `elevation`

Alias soportados de columnas:

- `segment_name`: `segment`, `segmento`
- `latitude`: `lat`, `y`
- `longitude`: `lon`, `lng`, `x`
- `elevation`: `elev`, `altitude`, `altura`

## Ejemplo CSV

```csv
segment_name,kp,latitude,longitude,elevation
Segmento_Norte,0.0,10.12345,-72.45678,35.0
Segmento_Norte,0.5,10.12395,-72.45720,35.4
Segmento_Norte,1.0,10.12450,-72.45780,36.2
```

## Reglas de validación

- `segment_name` debe existir en la tabla `Segment`.
- `kp`, `latitude`, `longitude` deben ser numéricos.
- `elevation` es opcional y numérica si se envía.
- Se utiliza unicidad por `segment + kp`.

## Resultado de la importación

La respuesta retorna un resumen:

- `processed`: total de filas leídas
- `created`: filas insertadas
- `updated`: filas actualizadas
- `skipped`: filas omitidas (por ejemplo, duplicadas con `update_existing=false`)
- `errors`: lista de errores por fila
- `success`: `true` si no hubo errores

## Interpolación posterior

Una vez cargado el perfil, se puede consultar ubicación por KP:

- `POST /linear-referencing-geospatial/interpolate`
- Body JSON:

```json
{
  "segment_name": "Segmento_Norte",
  "kp": 0.75
}
```

Si el `KP` no existe exacto, el sistema realiza interpolación lineal entre los puntos adyacentes.
