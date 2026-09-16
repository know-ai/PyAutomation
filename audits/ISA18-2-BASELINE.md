# ISA18-2-BASELINE — GATE-0

| Campo | Valor |
|---|---|
| **Spec** | SPEC-ISA18-2-P0P1 |
| **Fecha** | 2026-09-16 |
| **Entorno** | Árbol `github/PyAutomation`, SQLite `:memory:`, unittest local |
| **Estado** | Captura de laboratorio/planta **no ejecutada** en este ciclo |

## Métricas pedidas por la spec

| Métrica | Valor GATE-0 | Notas |
|---|---|---|
| RSS proceso SM | no capturado | Sin edge vivo en esta sesión |
| p95 ciclo SM / CVT | no capturado | No se tocó `ProcessType.set_value` ni CVT |
| Heap HMI (1 h) | no capturado | Sin navegación Playwright de 1 h |
| Filas `alarm_summary` pre-fix | n/a (SQLite de test) | El esquema v2 es aditivo |

## Invariantes de no-regresión asumidas

- Contrato SAF `PersistableRecord.alarm_create` + `sample_uuid` se conserva.
- Filtro Redux `isAnnunciatedAlarm` no se modificó.
- Sin dependencias nuevas.

El GATE-0 de planta (RSS/p95/heap) queda **pendiente** para el edge de lab antes de soak (GATE-7).
