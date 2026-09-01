# Changelog

## 2.8.2

- Suscripción a máquina: ya no fuerza `frozen` / `out_of_range` / `outlier` en el tag (default `false`). HMI Tags: checkboxes IAD visibles pero deshabilitados (motor IAD comentado en CVT).
- HMI `/alarms/definitions`: editar alarma rellena tipo, disparo, delays y descripción actuales (BOOL como true/false, no `1`).
- Alarmas `.iad`: la condición es calidad Bad/stale (On-Delay), no el PV analógico como BOOL. Al volver a Good (Acked) pasan a Normal; no se re-disparan mientras la señal siga Good.
- `@validate_types` ya no lanza KeyError si el kwarg está en la firma del método pero faltaba en el decorator (p. ej. `user` al actualizar/reconocer alarmas). `update_alarm` declara `user`.
- Arranque: `create_alarm` acepta `on_delay` / `off_delay` (y unidades) al recargar alarmas desde BD; ya no falla con KeyError y deja las alarmas sin cargar.
- Arranque: crear máquina con `identifier` ya existente es idempotente (no INSERT duplicado ni WARNING de historiador inalcanzable).
- `DB_ACTIVE_CONNECTIONS` cuenta solo backends PostgreSQL de este nodo (`application_name` `PyAutomationIO:{node_id}%` y el mismo `client_addr`). La alarma de umbral ya no suma conexiones de otros edges.
- HMI `/performance`: dashboard de ancho completo, tarjetas arrastrables/redimensionables (layout persistente, default agrupado por vitals → plano de datos → ops), tooltips operativos en el icono info y sin lede de desarrollo. Los botones de acción (workers, catálogo, tags derivados, SAF) muestran tooltip con efecto y riesgo.
- HMI detalle de máquina: hint permanente en suscripciones (tag de campo ausente = no mapeado en Tags/OPC UA) y segundo hint dinámico con las variables mínimas de cada motor (NPW/PPA: presiones; PFM/Observer: un punto o entrada/salida según el modelo, caudal/densidad). Sin toast ni banner de mapeo. Banner de llenado de buffer se refresca cada 400 ms y muestra barra de progreso. PFM/Observer: carga de modelos en 4/3 columnas (laptop+), títulos cortos (Detección, Flujo de Fuga, Tamaño de Fuga, Localización de Fuga), checklist de artefactos con scroll horizontal solo si el nombre no cabe y sin textos de transporte HTTPS/SSH. NPW/PPA/Observer: umbrales en una sola fila; NPW/PPA limitan umbrales a 1 decimal. NPW ya no muestra frecuencia de muestreo. DAQ/OPCUA ocultos por defecto (habilitar en Configuración → Esta estación); si se muestran, van antes de los motores de detección.
- HMI DomainConfigurable: al cargar artefactos se muestra el nodo destino (`NODE_ID` + host), la ruta en el volumen, barra de progreso HTTPS y toast con `destination_path`. `POST /api/machines/<name>/domain-config/files` devuelve `destination_path`, `files_written` y `message`. Sin canal SSH.
- HMI `/alarms/definitions`: filtro de texto (nombre o descripción) y desplegable de estado ISA 18.2. `GET /alarms/` acepta `q` y `state` antes de paginar.
- Alarmas ISA-18.2 On-Delay / Off-Delay (default 0 s, activación inmediata): el gestor no dispara ni limpia hasta que la condición se mantiene el tiempo configurado. API `GET/POST/PUT` y HMI (Pending/Clearing).

## 2.8.1

- DAQ: un `Read` OPC UA por ciclo y por cliente para todos los tags del mismo `scan_time` (DAQ-1000 y DAQ-500 cada uno su batch). Timeout configurable `AUTOMATION_DAQ_READ_TIMEOUT_S` (default 0.5 s, clamp 0.05–5).

- Dashboard de rendimiento del nodo: `GET /api/health/node` (snapshot O(1)), `MetricsSamplerWorker`, middleware HTTP y pantalla HMI `/performance` (admin/supervisor). Dependencia `psutil` para CPU/disco del host.
- Alarmas de rendimiento ISA-18.2 (`ALM.PERF.*`): evaluador con debounce en el sampler, `GET/PUT /api/settings/performance`, modal de ack/shelve en el dashboard y panel en Settings. `POST /api/alarms/unshelve/<name>`.
- Tags `SYS.PERF.*` persistidos en el historiador al conectar/reconectar la BD (evita filas SAF `alarm_summary` atascadas). Reintento en el sampler hasta que existan las 7 filas.
- HMI `/performance` (spec 07): gauges, paneles de subsistema, umbral en tarjeta, modal de configuración y estados ISA-18.2 (ACTIVA / ACK / SILENCIADA). PUT de umbrales para admin/supervisor/sudo.
- Socket HMI: reconexión Peewee en `hmi_sessions` (`ensure_bound_connection`) para no rechazar connect con `session_store_unavailable`.
- Alarmas de sistema (NTP OutOfSync): `create_tag(..., skip_validation=True)` para nombres internos multi-edge.
- HMI: layout del card NTP contenido dentro del tile.
- Controles operativos en `/performance`: widgets de workers, catálogo y tags derivados; `POST /api/admin/workers/restart`, `/saf/retry`, `/saf/reset`, `/catalog/sync`, `/catalog/clean-orphans`, `/tags/rebuild-derived`. Roles admin/supervisor (destructivo admin); auditoría en Events. Runbook actualizado.
