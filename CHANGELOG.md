# Changelog

## 2.8.1

- Dashboard de rendimiento del nodo: `GET /api/health/node` (snapshot O(1)), `MetricsSamplerWorker`, middleware HTTP y pantalla HMI `/performance` (admin/supervisor). Dependencia `psutil` para CPU/disco del host.
- Alarmas de rendimiento ISA-18.2 (`ALM.PERF.*`): evaluador con debounce en el sampler, `GET/PUT /api/settings/performance`, modal de ack/shelve en el dashboard y panel en Settings. `POST /api/alarms/unshelve/<name>`.
- HMI `/performance` (spec 07): gauges, paneles de subsistema, umbral en tarjeta, modal de configuración y estados ISA-18.2 (ACTIVA / ACK / SILENCIADA). PUT de umbrales para admin/supervisor/sudo.
- Socket HMI: reconexión Peewee en `hmi_sessions` (`ensure_bound_connection`) para no rechazar connect con `session_store_unavailable`.
- Alarmas de sistema (NTP OutOfSync): `create_tag(..., skip_validation=True)` para nombres internos multi-edge.
- HMI: layout del card NTP contenido dentro del tile.
