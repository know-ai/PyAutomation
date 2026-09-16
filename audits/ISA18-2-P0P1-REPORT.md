# ISA18-2-P0P1-REPORT — remediación alarmas ISA 18.2

| Campo | Valor |
|---|---|
| **Spec** | SPEC-ISA18-2-P0P1 |
| **Fecha** | 2026-09-16 |
| **Producto** | PyAutomationIO (`automation/` + `hmi/src/`) |
| **Alcance entregado** | P0-1…P0-6 + P1-1…P1-3 en código y tests SQLite |
| **Fuera de este ciclo** | GATE-3 lab PG, GATE-4 p95/heap medidos, GATE-5 Playwright, GATE-7 soak 24 h, GATE-8 smoke 48 h |

## Resumen ejecutivo

El historial de alarmas pasó de **una fila mutada por activación** a **append-only**: cada transición A–E escribe exactamente una fila en `alarm_summary` (`from_state`/`to_state` canónicos). El catálogo gana `last_transition_ts` para que el footer ordene RTN Unack sin borrar el timestamp de disparo. El backend anuncia B ∪ C ∪ D por `annunciate_status`. `acknowledge()` es no-op fuera de B/D. El SM se restaura en `reload=True` sin re-entrar `on_enter_*`.

Veredicto post-fix (código + T-01…T-11): **SM B+ / historial B / footer A−**. No se declara «Terminado» de la spec §13 mientras falten soak/smoke de planta.

Extensión 2026-09-16: [ISA18-2-COMPLEXITY-REPORT.md](./ISA18-2-COMPLEXITY-REPORT.md) (hot path O(1) en N; worker de transiciones).

## Gates

| Gate | Criterio | Resultado |
|---|---|---|
| GATE-0 | Baseline RSS/p95/heap | **PENDIENTE planta** — ver [ISA18-2-BASELINE.md](./ISA18-2-BASELINE.md) |
| GATE-1 | CA-P0-1…P0-6 | **PASS código** (T-01…T-11, I-01, selector/CSS/i18n en árbol) |
| GATE-2 | T-01…T-11 CI | **PASS** `unittest automation.tests.test_alarms_isa18_history` (13 tests, 2026-09-16) |
| GATE-3 | I-01…I-04 lab PG | **PARCIAL** — I-01 PASS en SQLite/manager. I-02…I-04 HTTP/Socket/SAF lab **pendientes** |
| GATE-4 | R-01…R-03 ±10 % | **PENDIENTE** medición. Regresión funcional: `test_alarms`, `test_alarm_delays`, `TestPerfAlarmAutoClear`, `TestAlarmSummarySafIdempotency` PASS |
| GATE-5 | V-01, V-02 visual | **PENDIENTE** — HMI sin runner de tests (AP-12: no se añadió Vitest). CSS/i18n en árbol |
| GATE-6 | CA-P1-* | **PASS código** (migración aditiva, `operator_id` en ack, reload SM) |
| GATE-7 | Soak 24 h | **PENDIENTE** |
| GATE-8 | Smoke 48 h un edge | **PENDIENTE** |

## Criterios de aceptación globales

| ID | Resultado | Evidencia |
|---|---|---|
| CA-G-01 | **PASS** | T-01…T-04: 3 / 3 / 5 / 7 filas |
| CA-G-02 | **PASS** | `AlarmSummary.put` / `AlarmSummary.update` / `put_record_on_alarm_summary` = 0 en `automation/` |
| CA-G-03 | **PASS** | T-01 C→E y T-02 D→E escriben `Cleared` |
| CA-G-04 | **PASS** | T-03: D→B inserta `Unack Alarm` y conserva RTN |
| CA-G-05 | **PASS** | T-04: 7 filas, sin colapsar |
| CA-G-06 | **PASS código** | Filtro Redux intacto + `last_transition_ts`; I-01 backend B+C+D |
| CA-G-07 | **PASS código** | `.footer-alarm-row--rtnun` ámbar, `--unack` blink, `--acked` estático |
| CA-G-08 | **PASS código** | `annunciate_status == Annunciated`; GET `/alarms/active_alarms` retorna la lista |
| CA-G-09 | **PASS** | T-07 / T-08: 0 INSERT |
| CA-G-10 | **PASS** | T-01 `operator_id=1` en B→C; T-02 `operator_id=7` en D→E; A→B/B→D nulos |
| CA-G-11 | **PASS** | `test_p13_reload_restores_sm`: 1 fila D→E |
| CA-G-12 | **PASS código** | `TestAlarmSummarySafIdempotency` PASS; contrato `alarm_create` |
| CA-G-13 | **PENDIENTE p95** | Hot path CVT no modificado |
| CA-G-14 | **PENDIENTE heap** | Footer/selector acotados al top-3 |
| CA-G-15 | **PENDIENTE soak** | Auto-clear PERF sigue registrando B→D→E (T-06) |
| CA-G-16 | **PASS** | Esta nota + [AUDIT_ISA18_2_ALARMS.md](./AUDIT_ISA18_2_ALARMS.md) |

## P0 / P1 por ítem

| Ítem | Estado |
|---|---|
| P0-1 `last_transition_ts` + selector | Hecho. `on_enter_rtn_unack` **no** anula `timestamp`. |
| P0-2 CSS/i18n B vs D | Hecho. Claves canónicas, sin mnemonic `RTNUN` en HMI. |
| P0-3 filtro B∪C∪D | Hecho. `get_lasts_active_alarms` + `last_active_alarms` + GET lista. |
| P0-4 dispatcher INSERT | Hecho. `_record_transition`; `put_record_on_alarm_summary` eliminado. |
| P0-5 T-01…T-11 SQLite | Hecho. Sin mock de `AlarmSummary`. |
| P0-6 `acknowledge()` no-op | Hecho. Guard antes de Event/INSERT; retorna `False`. |
| P1-1 schema v2 | Hecho. Columnas aditivas + backfill `schema_version=1`. Columna `state` conservada. |
| P1-2 `operator_id` | Hecho. JWT/`user.id` → `acknowledge(operator_id=…)`. |
| P1-3 reload SM | Hecho. `_force_state` sin `on_enter_*`. |

## Waivers / desviaciones documentadas

1. **Catálogo vs historial:** el catálogo `Alarms.state` sigue usando nombres ISA (`Unacknowledged`, `RTN Unacknowledged`, `Normal`). El historial persiste strings canónicos de la spec (`Unack Alarm`, `RTN Unack`, `Cleared`). Lectura nueva acepta ambas (`history_name_from_isa`).
2. **`operator_id`:** `IntegerField` (no FK a `users`) para no romper el orden de `create_tables` en tests.
3. **GET `/alarms/active_alarms`:** la spec CA-P0-3-2 manda devolver la lista B+C+D. El endpoint dejó de devolver `true/false`. El HMI no lo consume (usa socket + catálogo).
4. **V-01/V-02:** no hay runner JS en el HMI; no se añadió Vitest (AP-12).
5. **Ack en C:** el guard de servicio solo transiciona B y D. Ack en C es no-op (0 INSERT), alineado con INV-07 y con `from_state == to_state`.
6. **`sample_uuid`:** `uuid4()` por transición para no colapsar B↔D en el mismo ms (INV-01). Replay SAF sigue siendo idempotente por uuid del payload.

## Hallazgos adicionales (no corregidos — fuera de P0/P1)

- `AlarmState.get_state_by_name` compara un `Enum` con `AlarmAttrs` (eq siempre falso). El reload no depende de ese método.
- `GET /alarms/active_alarms` cambió de booleano a lista: clientes externos que esperaban boolean quedan rotos a propósito según spec.
- Retención ≥ 1 año, latching configurable, silence/disable/priority, coalescing de chatter y rediseño de `/alarms` siguen en P2.

## Cómo reproducir GATE-2

```bash
cd github/PyAutomation
./venv/bin/python -m unittest automation.tests.test_alarms_isa18_history -v
```
