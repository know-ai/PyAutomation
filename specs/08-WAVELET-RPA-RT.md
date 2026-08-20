# 08 — Filtro Wavelet en Tiempo Real (DWT por bloques)

## Objetivo

Filtrado wavelet desacoplado del hot path OPC/CVT, sincronizado al `sample_interval` de la máquina de estado suscriptora, con propagación de calidad OPC al tag derivado `.f`.

## Arquitectura

1. **Hot path (`Tag.set_value`)**: deadband único; escribe valor raw + `quality`; encola muestra O(1) en el worker si `filter_enabled=True`.
2. **`WaveletWorker`**: tick ~50 ms; por cada tag registrado publica en `.f` cuando `now >= next_pub`, usando DWT por ventana deslizante (`WaveletBlockFilter`).
3. **Tag derivado `nombre.f`**: la SM se suscribe a este tag cuando el source tiene filtro habilitado.
4. **Persistencia**: `filter_persist=True` registra el tag `.f` en el historificador al crear/actualizar el source (`_sync_wavelet_runtime`).

## Calidad OPC

| Ingest | Estado | Publicación `.f` |
|---|---|---|
| GOOD + buffer OK | `ok` | `quality=GOOD`, valor filtrado |
| GOOD + warmup | `warmup` | `quality=UNCERTAIN` |
| BAD / NaN / inf | `hold` | `quality=UNCERTAIN`, último valor bueno |
| Sin datos | `no_data` | sin publicación |

Módulo: `automation/signal_conditioning/quality.py` (`GOOD=1.0`, `UNCERTAIN=0.5`, `BAD=0.0`).

API observabilidad: `GET /api/tags/{name}/filter/status` expone `bad_samples_dropped`, `last_publication_quality`, `last_good_value`.

## Configuración (columnas `Tags`)

| Columna | Default | Descripción |
|---------|---------|-------------|
| `filter_enabled` | `false` | Activa el pipeline wavelet |
| `filter_wavelet` | `db4` | Wavelet PyWavelets |
| `filter_level` | `4` | Niveles DWT |
| `filter_threshold_factor` | `3.0` | Multiplicador σ (soft threshold) |
| `filter_persist` | `false` | Historizar tag `.f` |

**Columnas eliminadas (2026-08-19):** `gaussian_filter`, `gaussian_filter_threshold`, `gaussian_filter_r_value`, `process_filter`.

## Integración SM

- `subscribe_to(tag)` resuelve `tag.f` si `filter_enabled`.
- Registra el tag source en `WaveletWorker` con `sample_interval` de la SM (o `interval` de ejecución en modo legado).

## Legacy eliminado

- Decorador `@filter` (Kalman/Gaussian) y archivos `automation/tags/filter.py`, `automation/filter/__init__.py`.
- Páginas Dash `/filter` y componente `gaussian_filter.py`.
- Columnas SQL legacy vía `DBManager._drop_legacy_tag_columns()`.

## Módulos

- `automation/signal_conditioning/` — anillo, DWT, calidad, helpers `.f`
- `automation/workers/wavelet_worker.py` — worker sincronizado
- `hmi/src/components/WaveletFilterPanel.tsx` — configuración operador
- `hmi/src/pages/Performance.tsx` — widget filtros activos

## Tests

`automation/tests/test_wavelet_filter.py` — 14 tests unitarios (naming, ring, HOLD/UNCERTAIN, deadband, publish quality).

## Certificación pendiente

- Soak RSS 24 h (**CA-NF-2**)
- Golden trace offline (**CA-WF-1**)
- Integración SM + `.f` en CI (**CA-WF-2**)
