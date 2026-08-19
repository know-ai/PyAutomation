# Documento 03: Monitor NTP en edge

| Campo | Valor |
|---|---|
| **Versión** | 2.0 |
| **Fecha** | 2026-08-19 |
| **Estado** | Implementado (Fase A+B+v2 universal) |
| **Auditoría** | [AUDIT_NTP_TIME_SYNC.md](../audits/AUDIT_NTP_TIME_SYNC.md) |

## Alcance

Monitor SNTP no bloqueante con **IPv4/IPv6**, reintentos con backoff, detección de saltos bruscos, diagnóstico de fallos y compatibilidad documentada con servidores Linux/Windows. Alarmas ISA-18.2; API/HMI; columnas NTP en `Nodes`.

## Componentes

| Pieza | Ruta |
|---|---|
| Cliente SNTP universal | `automation/time/ntp_monitor.py` |
| Config | `automation/time/ntp_config.py` |
| Worker | `automation/workers/ntp_monitor.py` |
| Alarmas | `automation/utils/clock_alarms.py` |
| API | `GET/PUT /api/settings/clock`, `GET/POST /api/system/clock(/check)` |
| Health | bloque `clock` en `/api/health/system` |
| HMI | `ClockSyncPanel`, `ClockBadge` |
| Runbook | `docs/ntp-deployment.md` |

## Variables de entorno

`AUTOMATION_NTP_SERVERS`, `AUTOMATION_NTP_CHECK_INTERVAL_S`, `AUTOMATION_NTP_WARN_OFFSET_MS`, `AUTOMATION_NTP_ALARM_OFFSET_MS`, `AUTOMATION_NTP_STEP_THRESHOLD_MS`, `AUTOMATION_NTP_FAIL_CLOSED`, `AUTOMATION_NTP_ENABLED`, `AUTOMATION_NTP_AUTH_TYPE` (reservado P3).

Prioridad: **HMI / app_config.json > env (solo bootstrap) > defaults**.

## Criterios de aceptación

| ID | Criterio |
|---|---|
| CA-NTP-01 … 06 | Monitor base, alarmas, transiciones |
| CA-NTP-14 | Hostname → IPv6 exitoso |
| CA-NTP-15 | Falla IPv6, éxito IPv4 |
| CA-NTP-16 | Failover segundo servidor |
| CA-NTP-17 | 3 fallos consecutivos → alarma |
| CA-NTP-18 | Salto brusco → evento, sin alarma si offset OK |
| CA-NTP-19 | HMI muestra `last_error` / `auth_required_detected` |
| CA-NTP-20 | Soak 24 h 2-edge (Fase C) |

Tests: `automation/tests/test_ntp_monitor.py`.

## Pendiente (Fase C / P3)

- Soak 2-edge en planta (CA-NTP-20)
- Consola central multi-edge
- Autenticación simétrica / NTS (P3)
