# Observabilidad externa (Prometheus / Grafana)

PyAutomationIO **no** expone un exporter nativo `/metrics` de Prometheus. El contrato operativo es `GET /api/health/node` (copia O(1) del sampler, cada 5 s).

## Scrape JSON (opcional)

Un sidecar (Telegraf `inputs.http` + `json_v2`, o Grafana Infinity) puede pollar:

```
https://<edge>:8050/api/health/node
```

Campos útiles: `HOST_CPU_PERCENT`, `HOST_DISK_USED_PERCENT`, `HOST_NTP_ABS_OFFSET_MS`, `HOST_PEER_DOWN`, `SAF_QUEUE_DEPTH`, `SAF_REPLICATION_LAG_MS`, `HOST_SSD_WEAR_PERCENT`.

Requiere el mismo TLS y token de operador que la HMI. No scrapear `/api/health/system` a 1 Hz: recalcula en cada llamada.

## Loki

Los logs van a **stdout** del contenedor (`docker logs`). Un Promtail/Alloy en el host puede enviarlos a Loki. No hay agente Loki embebido (veredicto C en [AUDIT_LOGGING.md](../audits/AUDIT_LOGGING.md)).

## Alarmas

Las alarmas de planta son ISA-18.2 (`ALM.PERF.*`, `ALM.NTP.OutOfSync`), no reglas de Grafana. Grafana es un espejo, no la fuente de verdad.
