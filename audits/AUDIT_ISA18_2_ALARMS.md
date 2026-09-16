# Auditoría ISA 18.2 — Gestión de alarmas (ciclo de vida, historial, footer HMI)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Alcance** | Máquina de estados, historial `AlarmSummary`, acknowledgment, RTN Unack, re-disparo, footer «últimas 3» |
| **Norma** | ANSI/ISA-18.2-2016 — Management of Alarm Systems for the Process Industries (§9 presentación, §11 historial) |
| **Fecha** | 2026-09-16 (auditoría) · **remediación P0/P1 2026-09-16** · **cierre O(1) v2 2026-09-16** · **cierre P1 v3 2026-09-16** · **cierre PG lab v2 2026-09-16** |
| **Evidencia** | Código + T-01…T-11 + T-90…T-100 + T-64/T-64b + EXPLAIN PG 1 M + E2E OPC/Redis/restart |
| **Sustituye** | `docs/auditoria-modulo-alarmas-isa-18-2.md` (2026-06-20; delays/RTNUN/HMI desactualizados) |
| **Complementa** | [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md) (`condition_met`), [AUDIT_HMI.md](./AUDIT_HMI.md), [AUDIT_LOGGING.md](./AUDIT_LOGGING.md), [AUDIT_NODE_PERFORMANCE_DASHBOARD.md](./AUDIT_NODE_PERFORMANCE_DASHBOARD.md) |
| **Informe de remediación** | [ISA18-2-P0P1-REPORT.md](./ISA18-2-P0P1-REPORT.md) · [ISA18-2-COMPLEXITY-REPORT.md](./ISA18-2-COMPLEXITY-REPORT.md) · [ISA18-2-EXPLAIN.md](./ISA18-2-EXPLAIN.md) · [ISA18-2-EXPLAIN-PG.md](./ISA18-2-EXPLAIN-PG.md) · [ISA18-2-E2E-REPORT.md](./ISA18-2-E2E-REPORT.md) · [ISA18-2-PARTITION-PLAN.md](./ISA18-2-PARTITION-PLAN.md) · [ISA18-2-P1-CLOSURE-REPORT.md](./ISA18-2-P1-CLOSURE-REPORT.md) · baseline [ISA18-2-BASELINE.md](./ISA18-2-BASELINE.md) |
| **Veredicto** | **B+** SM. **B** historial. **A** footer/frontend acotado. **A−** hot path (O(1); T-64 p99=2 µs; T-64b p99=23.7 µs; `on_tag_value`+OPC p99=106 µs ≤ INV-55 150 µs). GATE-30 PG **verde**. Terminado v3 **con waivers**. |
| **Clasificación** | Auditoría de conformidad + gap analysis + cierre P0/P1 + P1 v3 |

---

## 0. Respuesta directa (pregunta del footer)

**Una alarma en RTN Unack debe seguir saliendo en el footer hasta que el operador la reconozca.**

ISA 18.2 §9: las no reconocidas tienen prioridad visual. RTN Unack sigue siendo *unacknowledged*. El footer muestra lo que requiere atención, no solo la condición física activa.

Estado **post-P0/P1**:

| Superficie | ¿RTN Unack visible? | Evidencia |
|---|---|---|
| Footer Redux (`selectActiveAlarmsPreview`) | **Sí** — lee `top3Active` (≤ 3), filtro `isAnnunciatedAlarm` = B + C + D. Orden por `last_transition_ts` | `hmi/src/store/slices/alarmsSlice.ts` |
| Footer orden / color | **Sí** — `timestamp` de activación se conserva en D; `last_transition_ts` mueve la fila al top. B rojo+blink, C rojo estático, D ámbar | `alarms/__init__.py` `on_enter_rtn_unack` · `Footer.tsx` · `global.css` `--rtnun` |
| `GET /alarms/active_alarms` y `last_active_alarms` | **Sí** — filtro `annunciate_status == Annunciated` (B∪C∪D). GET paginado `page_size`≤50; socket `last_active_alarms` top-3 | `managers/alarms.py` · `resources/alarms.py` · I-01 |
| Página `/alarms` | **Sí**, badge ámbar `alarm-state-badge--rtnun` | `global.css` · `alarmState.ts` |

El query Redux **sigue siendo** `isAnnunciatedAlarm` (correcto). El backend ya no filtra por `alarm_status == active`.

---

## 1. Diagrama ISA 18.2 vs implementación

ISA (A–E) más tres estados de supresión que la norma también define:

```
                    [A] Normal (NORM)
                         │
                         │ condición anormal
                         ▼
                    [B] Unack Alarm (UNACK) ◄──────────────┐
                         │                                  │
                         │ operador ack                     │ condición reaparece
                         ▼                                  │
                    [C] Ack Alarm (ACKED)                   │
                         │                                  │
                         │ condición normal                 │
                         ▼                                  │
                    [E] Cleared / Normal                    │
                                                            │
        desde B, condición normal ──► [D] RTN Unack ────────┘
                         │
                         │ operador ack
                         ▼
                    [E] Cleared / Normal
```

Supresión (P0/P1 **no** generan historial): Shelved, Suppressed By Design, Out Of Service.

Nombres persistidos en `alarm_summary.from_state` / `to_state` (canónicos spec):

| Símbolo | Historial | Catálogo ISA | `annunciate_status` |
|---|---|---|---|
| A | Normal | Normal | Not Annunciated |
| B | Unack Alarm | Unacknowledged | Annunciated |
| C | Ack Alarm | Acknowledged | Annunciated |
| D | RTN Unack | RTN Unacknowledged | Annunciated |
| E | Cleared | Normal | Not Annunciated |

---

## 2. Contrato de historial (post-P0-4)

`_record_transition(from_state, to_state)` es el único escritor. Guardas:

- `from_state == to_state` → no-op
- destino Shelved / DSUPR / OOSRV → WARNING, sin fila
- resto → INSERT `AlarmSummary` + UPDATE catálogo (`state`, `last_transition_*`) + SAF `alarm_create`

C→E y D→E persisten `to_state = Cleared`. El SM/catálogo vuelven a `Normal`.

`sample_uuid` es `uuid4()` por transición (INV-01: no colapsar B↔D en el mismo ms). Replay SAF idempotente por uuid del payload.

---

## 3. Gaps (IDs conservados)

### GAP-01: Historial no es una fila por transición — **CERRADO (P0-4)**

Dispatcher INSERT-only. T-01 = 3, T-02 = 3, T-03 = 5, T-04 = 7. `put_record_on_alarm_summary` eliminado.

### GAP-02: C→E / D→E sin rastro Cleared — **CERRADO (P0-4)**

`on_enter_normal` registra `Cleared` si el origen es Ack / RTN Unack / Unack.

### GAP-03: Re-disparo D→B pisa la fila A→B — **CERRADO (P0-4)**

Cada transición es INSERT. T-03 conserva RTN y añade Unack.

### GAP-04: Footer pierde RTN por `timestamp = None` — **CERRADO (P0-1)**

`on_enter_rtn_unack` no anula `timestamp`. Selector ordena por `last_transition_ts`.

### GAP-05: Footer no distingue B vs D — **CERRADO (P0-2)**

`.footer-alarm-row--unack` / `--acked` / `--rtnun`. i18n `alarms.states.RTN Unack` = «RTN sin reconocer». Snapshot planta (GATE-5) pendiente.

### GAP-06: Backend «active» excluye RTN Unack — **CERRADO (P0-3)**

Filtro `annunciate_status == Annunciated`. I-01 PASS.

### GAP-07: SM no se restaura al hidratar — **CERRADO (P1-3)**

`reload=True` + estado persistido → `_force_state` sin `on_enter_*`. `test_p13_reload_restores_sm`: 1 fila D→E.

### GAP-08: Label `RTNUN` / ack en Normal ensucia historial — **CERRADO (P0-2, P0-6)**

Badge usa `normalizeAlarmState` + `t("alarms.states." + canonical)`. `acknowledge()` retorna `False` fuera de B/D **antes** de Event/INSERT. T-07/T-08.

### GAP-09: Schema incompleto — **PARCIAL (P1-1/P1-2 cerrados; retención P2)**

Columnas v2: `from_state`, `to_state`, `event_time`, `operator_id`, `condition_met`, `condition_value`, `schema_version`. Columna legacy `state` conservada. Retención ≥ 1 año = P2.

### GAP-10: Latching / silence / prioridad / tests T-03–T-04 — **PARCIAL**

Tests T-01…T-11 contra SQLite real: **CERRADO**. Latching configurable, silence/disable/priority ISA: **P2**. PERF/QUALITY auto-clear documentado; T-06 registra A→B→D→E.

---

## 4. Schema actual (v2, aditivo)

```
alarm_summary:
  id | alarm_id | state_id | alarm_time | ack_time | area | sample_uuid
     | from_state | to_state | event_time | operator_id
     | condition_met | condition_value | schema_version

alarms (catálogo):
  … | last_transition_ts | last_transition_from | last_transition_to
```

Migración: `automation/migrations/001_alarm_summary_v2.py` + `AlarmSummary.ensure_schema()` / `ensure_alarm_delay_schema()`. Idempotente. Rollback = DROP de columnas nuevas; **no** borra filas.

Filas históricas: `schema_version = 1`, `from_state = to_state = state` (nombre ISA), `event_time = alarm_time`.

---

## 5. Footer: query actual

```
filter: isAnnunciatedAlarm(state) || delay_phase in {pending, clearing}
sort:   last_transition_ts DESC  (fallback timestamp, luego 0)
slice:  0, 3
```

Backend `get_lasts_active_alarms`:

```
annunciate_status == "Annunciated"
sort last_transition_ts || timestamp
```

B rojo parpadeante · C rojo estático más claro · D ámbar + «RTN sin reconocer».

---

## 6. Tests T-01…T-11 (SQLite real, 2026-09-16)

Sin mock de `AlarmSummary.create` ni `Alarms.update`.

| Test | Filas | `to_state` | Veredicto |
|---|---|---|---|
| **T-01** A→B→C→E | 3 | Unack Alarm, Ack Alarm, Cleared | **PASS** (`operator_id` en B→C) |
| **T-02** A→B→D→E | 3 | Unack Alarm, RTN Unack, Cleared | **PASS** (`timestamp` D = activación; `operator_id` en D→E) |
| **T-03** A→B→D→B→C→E | 5 | … Unack, RTN, Unack, Ack, Cleared | **PASS** |
| **T-04** oscilación | 7 | B↔D + ack + Cleared | **PASS** |
| **T-05** A→A | 0 | — | **PASS** |
| **T-06** PERF auto-clear | 3 | Unack, RTN Unack, Cleared | **PASS** |
| **T-07** ack en A | 0 | — | **PASS** |
| **T-08** ack en E | 0 | — | **PASS** |
| **T-09** same-state | 0 | — | **PASS** |
| **T-10** Shelved | 0 | WARNING | **PASS** |
| **T-11** `last_transition_ts` monótono | — | — | **PASS** |
| **P1-3** reload RTN | 1 | Cleared (D→E) | **PASS** |
| **I-01** B∪C∪D | 3 nombres | — | **PASS** |

Regresión: `test_alarms`, `test_alarm_delays`, `TestPerfAlarmAutoClear`, `test_acknowledge_all`, `TestAlarmSummarySafIdempotency` **PASS**.

Footer CA:

| CA | Resultado |
|---|---|
| **CA-F-01** D visible hasta ack | **PASS código** (filtro + sort). Visual planta pendiente |
| **CA-F-02** D ≠ B visual | **PASS código** (clases CSS). Snapshot pendiente |
| **CA-F-03** re-disparo actualiza, no duplica fila de UI | **PASS** (SM + historial) |
| **CA-F-04** ≤ 2 s | **PASS** (sin cambio) |
| **CA-F-05** ack desde footer | **PASS** (sin cambio) |

---

## 7. Criterios globales

| ID | Criterio | Resultado |
|---|---|---|
| **CA-01** | 5 estados explícitos | **PASS** |
| **CA-02** | D → B implementada y registrada | **PASS** (T-03) |
| **CA-03** | Una entrada por transición | **PASS** |
| **CA-04** | Append-only | **PASS** |
| **CA-05** | Historial sobrevive reinicio + SAF | **PASS código** (uuid + replay). Soak pendiente |
| **CA-06** | Footer muestra RTN hasta ack | **PASS código** |
| **CA-07** | Distinción visual D vs B | **PASS código** |
| **CA-08** | Socket B→D, D→B, D→E | **PASS** (`@put_alarm_state` / `on.alarm`) · I-03 lab pendiente |
| **CA-09** | Ack D → E | **PASS** |
| **CA-10** | Ack de D invalidado al re-disparar | **PASS** |
| **CA-11** | Historial filtrable | **PASS** (`to_state` + `state` legacy) |
| **CA-12** | API no borra historial | **PASS** |

---

## 8. Backlog residual (P2)

| Orden | Fix | Estado |
|---|---|---|
| **P0-1…P0-6** | timestamp, CSS, filtro, INSERT, tests, ack no-op | **Hecho** |
| **P1-1…P1-3 schema** | schema v2, operator_id, reload SM | **Hecho** |
| **P1 v3 cola/health/flag/HMI** | maxlen, worker health, `ALARM_SYNC_DRAIN`, paginación | **Hecho** |
| **P1 lab PG (PG-CLOSURE-v2)** | GATE-30 EXPLAIN 1 M, T-64b, paginación OFFSET, índices | **Hecho** (GATE-30 verde) |
| **P2-1** | Latching por alarma; retención ≥ 1 año (tabla archivo) | Abierto — plan en [ISA18-2-PARTITION-PLAN.md](./ISA18-2-PARTITION-PLAN.md) |
| **P2-2** | silence / disable / priority ISA | Abierto |
| **P2-3** | Coalescing de chatter | Abierto |
| **Planta / E2E residual** | OPC write, SAF replay, Playwright footer 2 s, 500 tags×100 ms | Abierto (waivers W-PG-01…09) |

P0-4 no mezcló reset SAF ni `ProcessType.set_value`.

---

## 9. Archivos clave

| Pieza | Ruta |
|---|---|
| Dispatcher + SM + reload | `automation/alarms/__init__.py` |
| Nombres canónicos | `automation/alarms/states.py` |
| Manager / filtro anunciadas | `automation/managers/alarms.py` |
| Persistencia INSERT + SAF | `automation/logger/alarms.py` · `dbmodels/alarms.py` |
| Migración v2 | `automation/migrations/001_alarm_summary_v2.py` |
| SAF uuid | `persistence/records.py` `alarm_create` |
| API ack + lista activa | `modules/alarms/resources/alarms.py` |
| Footer | `hmi/src/layouts/Footer.tsx` · `store/slices/alarmsSlice.ts` |
| CSS / i18n | `hmi/src/styles/global.css` · `locales/{es,en}.json` |
| Tests | `test_alarms_isa18_history.py` · `test_alarms_complexity.py` · `test_alarms_complexity_scale.py` · `test_alarms_p1_closure.py` · `test_alarms_pg_real_objects.py` · `test_alarms_e2e_opc.py` · `test_alarms_hot_path_real_scan.py` · `test_alarms_multiworker_pg_redis.py` · `test_alarms_pg_restart.py` · `test_alarms_pg_pagination.py` |
| Runtime O(1) | `automation/alarms/runtime.py` · `GET /api/health/alarms` |
| Paginación | `automation/alarms/pagination.py` · `alarms/config.py` · `GET /api/alarms/footer` |

---

## 12. Cierre P1 v3 (SPEC-ISA18-2-CLOSURE-v3)

Hot path DAS: enqueue **sin lock**, `deque(maxlen=100_000)`, sin drain en producción. Worker con heartbeat; health expone `transition_worker_alive` y `worker_lag_ms` p50/p95/p99. Store HMI: `top3Active` ≤ 3, `page` ≤ 50, `history` ≤ 100.

Evidencia: [ISA18-2-P1-CLOSURE-REPORT.md](./ISA18-2-P1-CLOSURE-REPORT.md). GATE-26…32 y GATE-30 **verdes**. GATE-33…38: ver [ISA18-2-E2E-REPORT.md](./ISA18-2-E2E-REPORT.md).

Veredicto v3: **A− hot path / A health / A frontend**. GATE-30 **verde**.

---

## 13. Cierre PG lab (SPEC-ISA18-2-PG-CLOSURE-v2)

Stack local real (nombres ≠ spec): `app_db` :32800, `compose-redis-session-1`, `opcua_simulator` :4840. Seed 500 + 1 000 010 historial.

| Gate | Veredicto |
|---|---|
| GATE-22-PG / GATE-30 | **VERDE** — 0 Seq Scan; Q1 0.10 ms … Q6 2.67 ms |
| GATE-29b T-64b | **VERDE** — p99=23.7 µs N=500 |
| GATE-32-PG | **VERDE** — OFFSET 450 = 2.92 ms |
| GATE-33 | PARCIAL — PK `bigint`, 0 FK; falta `event_time` en unique |
| GATE-34 / 38 | Ciclo 5 filas SQLite **PASS**; OPC write `BadUserAccessDenied` |
| GATE-35 | INV-55 **PASS** (p99 106 µs ≤ 150); CA-F6 50 µs **FAIL** CPython |
| GATE-36 | Redis **no** en hot path; 2 drainers 100/100 |
| GATE-37 | `docker restart app_db` filas=1 000 010; SAF replay no |

**Terminado v3 con waivers** (SHA `7ee3df9527c5141e8bc963b856cd569f95aa8a1e`). No pleno.

---

## 11. Contrato O(1) (SPEC-ISA18-2-CLOSURE-v2)

Hot path DAS: `AlarmTagObserver` → `check_condition` → enqueue. **Prohibido** en DAS: `_record_transition`, INSERT/UPDATE, `on.alarm`.

Cold path: `AlarmTransitionWorker` (arranque en `PyAutomation.__start_workers`). Tests drenan solo si `AlarmConfig.is_sync_drain_allowed()`.

Evidencia: [ISA18-2-COMPLEXITY-REPORT.md](./ISA18-2-COMPLEXITY-REPORT.md), [ISA18-2-EXPLAIN.md](./ISA18-2-EXPLAIN.md), [ISA18-2-EXPLAIN-PG.md](./ISA18-2-EXPLAIN-PG.md).

CVT / `ProcessType.set_value` **no se tocaron**.

---

## 10. Changelog

| Fecha | Cambio |
|---|---|
| 2026-06-20 | Auditoría amplia en `docs/auditoria-modulo-alarmas-isa-18-2.md`. |
| 2026-09-16 | Auditoría canónica: veredicto **B− / D / C+**. T-01…T-04 con persistencia mockeada. |
| 2026-09-16 | Remediación SPEC-ISA18-2-P0P1. Historial append-only, footer RTN, filtro B∪C∪D, reload SM. T-01…T-11 SQLite real PASS. Veredicto **B+ / B / A−**. Soak/smoke pendientes. |
| 2026-09-16 | SPEC-ISA18-2-CLOSURE-v2: cola + worker, `check_condition` O(1) en N, `/api/health/alarms`, índices. p99 ~55 µs CPython (waiver 10 µs). |
| 2026-09-16 | SPEC-ISA18-2-CLOSURE-v3: maxlen 100k, health worker/lag, flag doble barrera, T-64 1M keys p99=2 µs, HMI paginado. GATE-30 PG waiver. Veredicto hot path **A−** / frontend **A**. |
| 2026-09-16 | SPEC-ISA18-2-PG-CLOSURE-v2: GATE-30 **verde** (EXPLAIN 1 M, 0 Seq Scan). T-64b p99=23.7 µs. E2E OPC read OK / write denied. Terminado v3 **con waivers**. SHA `7ee3df9527c5141e8bc963b856cd569f95aa8a1e`. |
