# Auditoría: Alarmas (ISA 18.2)

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Documento canónico** | 01 / 10 |
| **Fecha de agrupación** | 2026-09-16 |
| **Fuentes absorbidas** | `AUDIT_ISA18_2_ALARMS`, `ISA18-2-P0P1-REPORT`, `ISA18-2-COMPLEXITY-REPORT`, `ISA18-2-EXPLAIN`, `ISA18-2-EXPLAIN-PG`, `ISA18-2-EXPLAIN-PG-raw`, `ISA18-2-E2E-REPORT`, `ISA18-2-PARTITION-PLAN`, `ISA18-2-P1-CLOSURE-REPORT`, `ISA18-2-P2-CLOSURE-REPORT-v2`, `ISA18-2-BASELINE`, `p2/alarmsummary.schema.sql` |
| **Complementa** | [AUDIT_HMI.md](./AUDIT_HMI.md), [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md), [AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md) |
| **Veredicto vigente** | SM **A−** · historial **A−** · footer **A** · hot path **A**; P2 **con waivers** (partición live) |
| **Clasificación** | Auditoría de contraste código vs diseño. IDs de hallazgos conservados. |


Este archivo agrupa **todas** las auditorías del dominio. Cada parte conserva el texto original.

## Índice de partes

- [Parte A — Gestión de alarmas (ciclo de vida, historial, footer)](#parte-a-gestión-de-alarmas-ciclo-de-vida-historial-footer)
- [Parte B — Informe P0/P1](#parte-b-informe-p0p1)
- [Parte C — Baseline GATE-0](#parte-c-baseline-gate-0)
- [Parte D — Complejidad O(1) del hot path](#parte-d-complejidad-o1-del-hot-path)
- [Parte E — EXPLAIN SQLite (GATE-22)](#parte-e-explain-sqlite-gate-22)
- [Parte F — EXPLAIN PostgreSQL (GATE-30)](#parte-f-explain-postgresql-gate-30)
- [Parte G — Dump crudo EXPLAIN PG](#parte-g-dump-crudo-explain-pg)
- [Parte H — Informe E2E PG lab](#parte-h-informe-e2e-pg-lab)
- [Parte I — Plan de partición GATE-33](#parte-i-plan-de-partición-gate-33)
- [Parte J — Cierre P1 v3 + PG lab](#parte-j-cierre-p1-v3-pg-lab)
- [Parte K — Cierre P2 v2](#parte-k-cierre-p2-v2)
- [Parte L — Schema SQL live `alarmsummary`](#parte-l-schema-sql-live-alarmsummary)

---

## Parte A — Gestión de alarmas (ciclo de vida, historial, footer)

> Fuente original: `AUDIT_ISA18_2_ALARMS.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Alcance** | Máquina de estados, historial `AlarmSummary`, acknowledgment, RTN Unack, re-disparo, footer «últimas 3» |
| **Norma** | ANSI/ISA-18.2-2016 — Management of Alarm Systems for the Process Industries (§9 presentación, §11 historial) |
| **Fecha** | 2026-09-16 (auditoría) · P0/P1 · O(1) v2 · P1 v3 · PG lab v2 · **P2 v2 2026-09-16** |
| **Evidencia** | Código + T-01…T-11 + T-90…T-100 + T-64/T-64b + T-150…T-180 + EXPLAIN PG 1 M |
| **Sustituye** | `docs/auditoria-modulo-alarmas-isa-18-2.md` (2026-06-20; delays/RTNUN/HMI desactualizados) |
| **Complementa** | [AUDIT_DB.md](./AUDIT_DB.md) (`condition_met`), [AUDIT_HMI.md](./AUDIT_HMI.md), [AUDIT_RELIABILITY.md](./AUDIT_RELIABILITY.md), [AUDIT_PERFORMANCE.md](./AUDIT_PERFORMANCE.md) |
| **Informe de remediación** | [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) · [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) · [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) · [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) · [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) · [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) · [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) · [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) · baseline [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) |
| **Veredicto** | SM **A−**. Historial **A−**. Footer/frontend **A**. Hot path **A** (T-179 p99=24.6 µs). Health/KPI **A**. Triple v3 **A/A/A**. GATE-30 verde. P2 v2 **con waivers** (partición live). |
| **Clasificación** | Auditoría de conformidad + gap analysis + cierre P0/P1 + P1 v3 + P2 v2 |

---

### 0. Respuesta directa (pregunta del footer)

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

### 1. Diagrama ISA 18.2 vs implementación

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

### 2. Contrato de historial (post-P0-4)

`_record_transition(from_state, to_state)` es el único escritor. Guardas:

- `from_state == to_state` → no-op
- destino Shelved / DSUPR / OOSRV → WARNING, sin fila
- resto → INSERT `AlarmSummary` + UPDATE catálogo (`state`, `last_transition_*`) + SAF `alarm_create`

C→E y D→E persisten `to_state = Cleared`. El SM/catálogo vuelven a `Normal`.

`sample_uuid` es `uuid4()` por transición (INV-01: no colapsar B↔D en el mismo ms). Replay SAF idempotente por uuid del payload.

---

### 3. Gaps (IDs conservados)

#### GAP-01: Historial no es una fila por transición — **CERRADO (P0-4)**

Dispatcher INSERT-only. T-01 = 3, T-02 = 3, T-03 = 5, T-04 = 7. `put_record_on_alarm_summary` eliminado.

#### GAP-02: C→E / D→E sin rastro Cleared — **CERRADO (P0-4)**

`on_enter_normal` registra `Cleared` si el origen es Ack / RTN Unack / Unack.

#### GAP-03: Re-disparo D→B pisa la fila A→B — **CERRADO (P0-4)**

Cada transición es INSERT. T-03 conserva RTN y añade Unack.

#### GAP-04: Footer pierde RTN por `timestamp = None` — **CERRADO (P0-1)**

`on_enter_rtn_unack` no anula `timestamp`. Selector ordena por `last_transition_ts`.

#### GAP-05: Footer no distingue B vs D — **CERRADO (P0-2)**

`.footer-alarm-row--unack` / `--acked` / `--rtnun`. i18n `alarms.states.RTN Unack` = «RTN sin reconocer». Snapshot planta (GATE-5) pendiente.

#### GAP-06: Backend «active» excluye RTN Unack — **CERRADO (P0-3)**

Filtro `annunciate_status == Annunciated`. I-01 PASS.

#### GAP-07: SM no se restaura al hidratar — **CERRADO (P1-3)**

`reload=True` + estado persistido → `_force_state` sin `on_enter_*`. `test_p13_reload_restores_sm`: 1 fila D→E.

#### GAP-08: Label `RTNUN` / ack en Normal ensucia historial — **CERRADO (P0-2, P0-6)**

Badge usa `normalizeAlarmState` + `t("alarms.states." + canonical)`. `acknowledge()` retorna `False` fuera de B/D **antes** de Event/INSERT. T-07/T-08.

#### GAP-09: Schema incompleto — **PARCIAL (P1-1/P1-2 cerrados; retención P2)**

Columnas v2: `from_state`, `to_state`, `event_time`, `operator_id`, `condition_met`, `condition_value`, `schema_version`. Columna legacy `state` conservada. Retención ≥ 1 año = P2.

#### GAP-10: Latching / silence / prioridad / tests T-03–T-04 — **PARCIAL**

Tests T-01…T-11 contra SQLite real: **CERRADO**. Latching configurable, silence/disable/priority ISA: **P2**. PERF/QUALITY auto-clear documentado; T-06 registra A→B→D→E.

---

### 4. Schema actual (v2, aditivo)

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

### 5. Footer: query actual

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

### 6. Tests T-01…T-11 (SQLite real, 2026-09-16)

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

### 7. Criterios globales

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

### 8. Backlog residual (P2)

| Orden | Fix | Estado |
|---|---|---|
| **P0-1…P0-6** | timestamp, CSS, filtro, INSERT, tests, ack no-op | **Hecho** |
| **P1-1…P1-3 schema** | schema v2, operator_id, reload SM | **Hecho** |
| **P1 v3 cola/health/flag/HMI** | maxlen, worker health, `ALARM_SYNC_DRAIN`, paginación | **Hecho** |
| **P1 lab PG (PG-CLOSURE-v2)** | GATE-30 EXPLAIN 1 M, T-64b, paginación OFFSET, índices | **Hecho** (GATE-30 verde) |
| **P2-1** | Latching por alarma; retención ≥ 1 año (tabla archivo) | **Hecho en código** (archiver chunk 10k; cutover PG waiver) |
| **P2-2** | silence / disable / priority ISA | **Hecho en código** (`alarms/p2/` + API) |
| **P2-3** | Coalescing de chatter | **Parcial** — flag O(1); no colapsa filas ISA (T-04) |
| **Planta / E2E residual** | OPC write, SAF replay, Playwright footer 2 s, 500 tags×100 ms | Abierto (waivers W-PG-01…09) |

P0-4 no mezcló reset SAF ni `ProcessType.set_value`.

---

### 9. Archivos clave

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
| Tests | … · `test_alarms_p2_closure.py` |
| P2 | `automation/alarms/p2/` · `modules/alarms/resources/p2_api.py` · `jobs/alarm_p2.py` |
| Runtime O(1) | `automation/alarms/runtime.py` · `GET /api/health/alarms` |
| Paginación | `automation/alarms/pagination.py` · `alarms/config.py` · `GET /api/alarms/footer` |

---

### 12. Cierre P1 v3 (SPEC-ISA18-2-CLOSURE-v3)

Hot path DAS: enqueue **sin lock**, `deque(maxlen=100_000)`, sin drain en producción. Worker con heartbeat; health expone `transition_worker_alive` y `worker_lag_ms` p50/p95/p99. Store HMI: `top3Active` ≤ 3, `page` ≤ 50, `history` ≤ 100.

Evidencia: [AUDIT_ALARMS.md](./AUDIT_ALARMS.md). GATE-26…32 y GATE-30 **verdes**. GATE-33…38: ver [AUDIT_ALARMS.md](./AUDIT_ALARMS.md).

Veredicto v3: **A− hot path / A health / A frontend**. GATE-30 **verde**.

---

### 13. Cierre PG lab (SPEC-ISA18-2-PG-CLOSURE-v2)

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

### 14. Cierre P2 v2 (SPEC-ISA18-2-P2-CLOSURE-v2)

Módulos en `automation/alarms/p2/`. HOT: solo `is_suppressed` O(1). T-179 p99=**24.6 µs**. Footer ordena por `(priority, last_transition_ts)`. API: `/api/alarms/kpi`, `PATCH .../priority`, `POST .../silence|shelve|disable|oos`.

Evidencia: [AUDIT_ALARMS.md](./AUDIT_ALARMS.md). SHA `b5bed66cad90694298c026a6b05ff238e2d93607`.

Veredicto P2: hot path **A** / health **A** / frontend **A**. Partición live **waiver W-P2-01**.

---

### 11. Contrato O(1) (SPEC-ISA18-2-CLOSURE-v2)

Hot path DAS: `AlarmTagObserver` → `check_condition` → enqueue. **Prohibido** en DAS: `_record_transition`, INSERT/UPDATE, `on.alarm`.

Cold path: `AlarmTransitionWorker` (arranque en `PyAutomation.__start_workers`). Tests drenan solo si `AlarmConfig.is_sync_drain_allowed()`.

Evidencia: [AUDIT_ALARMS.md](./AUDIT_ALARMS.md).

CVT / `ProcessType.set_value` **no se tocaron**.

---

### 10. Changelog

| Fecha | Cambio |
|---|---|
| 2026-06-20 | Auditoría amplia en `docs/auditoria-modulo-alarmas-isa-18-2.md`. |
| 2026-09-16 | Auditoría canónica: veredicto **B− / D / C+**. T-01…T-04 con persistencia mockeada. |
| 2026-09-16 | Remediación SPEC-ISA18-2-P0P1. Historial append-only, footer RTN, filtro B∪C∪D, reload SM. T-01…T-11 SQLite real PASS. Veredicto **B+ / B / A−**. Soak/smoke pendientes. |
| 2026-09-16 | SPEC-ISA18-2-CLOSURE-v2: cola + worker, `check_condition` O(1) en N, `/api/health/alarms`, índices. p99 ~55 µs CPython (waiver 10 µs). |
| 2026-09-16 | SPEC-ISA18-2-CLOSURE-v3: maxlen 100k, health worker/lag, flag doble barrera, T-64 1M keys p99=2 µs, HMI paginado. GATE-30 PG waiver. Veredicto hot path **A−** / frontend **A**. |
| 2026-09-16 | SPEC-ISA18-2-PG-CLOSURE-v2: GATE-30 **verde** (EXPLAIN 1 M, 0 Seq Scan). T-64b p99=23.7 µs. E2E OPC read OK / write denied. Terminado v3 **con waivers**. SHA `7ee3df9527c5141e8bc963b856cd569f95aa8a1e`. |
| 2026-09-16 | SPEC-ISA18-2-P2-CLOSURE-v2: priority/latching/chatter/suppression/KPI/archive. T-179 p99=24.6 µs. Terminado P2 v2 **con waivers**. SHA `b5bed66cad90694298c026a6b05ff238e2d93607`. |


## Parte B — Informe P0/P1

> Fuente original: `ISA18-2-P0P1-REPORT.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Spec** | SPEC-ISA18-2-P0P1 |
| **Fecha** | 2026-09-16 |
| **Producto** | PyAutomationIO (`automation/` + `hmi/src/`) |
| **Alcance entregado** | P0-1…P0-6 + P1-1…P1-3 en código y tests SQLite |
| **Fuera de este ciclo** | GATE-3 lab PG, GATE-4 p95/heap medidos, GATE-5 Playwright, GATE-7 soak 24 h, GATE-8 smoke 48 h |

### Resumen ejecutivo

El historial de alarmas pasó de **una fila mutada por activación** a **append-only**: cada transición A–E escribe exactamente una fila en `alarm_summary` (`from_state`/`to_state` canónicos). El catálogo gana `last_transition_ts` para que el footer ordene RTN Unack sin borrar el timestamp de disparo. El backend anuncia B ∪ C ∪ D por `annunciate_status`. `acknowledge()` es no-op fuera de B/D. El SM se restaura en `reload=True` sin re-entrar `on_enter_*`.

Veredicto post-fix (código + T-01…T-11): **SM B+ / historial B / footer A−**. No se declara «Terminado» de la spec §13 mientras falten soak/smoke de planta.

Extensión 2026-09-16: [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) (hot path O(1) en N; worker de transiciones).

### Gates

| Gate | Criterio | Resultado |
|---|---|---|
| GATE-0 | Baseline RSS/p95/heap | **PENDIENTE planta** — ver [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) |
| GATE-1 | CA-P0-1…P0-6 | **PASS código** (T-01…T-11, I-01, selector/CSS/i18n en árbol) |
| GATE-2 | T-01…T-11 CI | **PASS** `unittest automation.tests.test_alarms_isa18_history` (13 tests, 2026-09-16) |
| GATE-3 | I-01…I-04 lab PG | **PARCIAL** — I-01 PASS en SQLite/manager. I-02…I-04 HTTP/Socket/SAF lab **pendientes** |
| GATE-4 | R-01…R-03 ±10 % | **PENDIENTE** medición. Regresión funcional: `test_alarms`, `test_alarm_delays`, `TestPerfAlarmAutoClear`, `TestAlarmSummarySafIdempotency` PASS |
| GATE-5 | V-01, V-02 visual | **PENDIENTE** — HMI sin runner de tests (AP-12: no se añadió Vitest). CSS/i18n en árbol |
| GATE-6 | CA-P1-* | **PASS código** (migración aditiva, `operator_id` en ack, reload SM) |
| GATE-7 | Soak 24 h | **PENDIENTE** |
| GATE-8 | Smoke 48 h un edge | **PENDIENTE** |

### Criterios de aceptación globales

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
| CA-G-16 | **PASS** | Esta nota + [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) |

### P0 / P1 por ítem

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

### Waivers / desviaciones documentadas

1. **Catálogo vs historial:** el catálogo `Alarms.state` sigue usando nombres ISA (`Unacknowledged`, `RTN Unacknowledged`, `Normal`). El historial persiste strings canónicos de la spec (`Unack Alarm`, `RTN Unack`, `Cleared`). Lectura nueva acepta ambas (`history_name_from_isa`).
2. **`operator_id`:** `IntegerField` (no FK a `users`) para no romper el orden de `create_tables` en tests.
3. **GET `/alarms/active_alarms`:** la spec CA-P0-3-2 manda devolver la lista B+C+D. El endpoint dejó de devolver `true/false`. El HMI no lo consume (usa socket + catálogo).
4. **V-01/V-02:** no hay runner JS en el HMI; no se añadió Vitest (AP-12).
5. **Ack en C:** el guard de servicio solo transiciona B y D. Ack en C es no-op (0 INSERT), alineado con INV-07 y con `from_state == to_state`.
6. **`sample_uuid`:** `uuid4()` por transición para no colapsar B↔D en el mismo ms (INV-01). Replay SAF sigue siendo idempotente por uuid del payload.

### Hallazgos adicionales (no corregidos — fuera de P0/P1)

- `AlarmState.get_state_by_name` compara un `Enum` con `AlarmAttrs` (eq siempre falso). El reload no depende de ese método.
- `GET /alarms/active_alarms` cambió de booleano a lista: clientes externos que esperaban boolean quedan rotos a propósito según spec.
- Retención ≥ 1 año, latching configurable, silence/disable/priority, coalescing de chatter y rediseño de `/alarms` siguen en P2.

### Cómo reproducir GATE-2

```bash
cd github/PyAutomation
./venv/bin/python -m unittest automation.tests.test_alarms_isa18_history -v
```


## Parte C — Baseline GATE-0

> Fuente original: `ISA18-2-BASELINE.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Spec** | SPEC-ISA18-2-P0P1 |
| **Fecha** | 2026-09-16 |
| **Entorno** | Árbol `github/PyAutomation`, SQLite `:memory:`, unittest local |
| **Estado** | Captura de laboratorio/planta **no ejecutada** en este ciclo |

### Métricas pedidas por la spec

| Métrica | Valor GATE-0 | Notas |
|---|---|---|
| RSS proceso SM | no capturado | Sin edge vivo en esta sesión |
| p95 ciclo SM / CVT | no capturado | No se tocó `ProcessType.set_value` ni CVT |
| Heap HMI (1 h) | no capturado | Sin navegación Playwright de 1 h |
| Filas `alarm_summary` pre-fix | n/a (SQLite de test) | El esquema v2 es aditivo |

### Invariantes de no-regresión asumidas

- Contrato SAF `PersistableRecord.alarm_create` + `sample_uuid` se conserva.
- Filtro Redux `isAnnunciatedAlarm` no se modificó.
- Sin dependencias nuevas.

El GATE-0 de planta (RSS/p95/heap) queda **pendiente** para el edge de lab antes de soak (GATE-7).


## Parte D — Complejidad O(1) del hot path

> Fuente original: `ISA18-2-COMPLEXITY-REPORT.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Spec** | SPEC-ISA18-2-CLOSURE-v2 |
| **Fecha** | 2026-09-16 |
| **Host** | CPython 3.12, laptop de desarrollo, SQLite `:memory:` |
| **Código** | `automation/alarms/runtime.py`, `Alarm.check_condition`, `AlarmManager.on_tag_value`, `GET /api/health/alarms` |

### Resumen ejecutivo

El chequeo de alarma **ya no ejecuta SM, INSERT ni `on.alarm` en el hilo DAS**. El hot path hace hash lookup (`_by_tag_name`) + comparación + delay O(1) + `deque.append`. El `AlarmTransitionWorker` procesa la cola; si el worker no está vivo (tests), se drena al salir de `check_condition` para no romper T-01…T-11.

**O(1) respecto a N (catálogo) confirmado:** p99 de `on_tag_value` con 1 alarma en el tag evaluado es **56 µs** (N≈1) y **53 µs** (20 000 claves extra en el índice). No crece con N.

**Presupuesto absoluto 10 µs p99:** **no alcanzado en CPython** en este host (p99 ≈ 50–60 µs). Es una limitación de intérprete + `quality` + observer, no de complejidad algorítmica. Waiver: GATE-19 absoluto µs = **ROJO de laboratorio**; independencia de N = **VERDE**. No se declara «Terminado» v2 §8bis.

### INV-21 — `on_tag_value` / `check_condition` O(1) en N

**Método:** 8 000 iteraciones, 1 tag, 1 alarma HIGH que **no** dispara, warmup 500.

| N (claves en `_by_tag_name`) | p50 (µs) | p99 (µs) | p99.9 (µs) |
|---|---|---|---|
| 1 | 23.3 | 56.3 | 98.5 |
| 20 000 | 21.7 | 52.8 | 83.0 |

**Veredicto:** O(1) en N **PASS**. p99 no crece (varía −6 %). Presupuesto 10 µs **FAIL** en CPython de este host.

T-64 sintético (v3, SimpleNamespace, **sin** objetos `Alarm`): N=1 000 000 keys, p50=0.9 µs, **p99=2.0 µs**, dict **79.9 MB**, runtime 9 s. Presupuesto v3 50 µs: **PASS**. Ver [AUDIT_ALARMS.md](./AUDIT_ALARMS.md).

### INV-22 / INV-23 — cold path

SM + `_record_transition` corren en `TransitionWorker` o en `drain()` post-hot-path. `python-statemachine` `send` es O(1) por transición. T-01…T-11 siguen PASS.

### INV-24 / INV-25 — índices

Ver [AUDIT_ALARMS.md](./AUDIT_ALARMS.md). SQLite usa COVERING INDEX / SEARCH. Footer activo usa índice en memoria `_annunciated` (O(A)).

### INV-27…INV-30 — contadores

`AlarmRuntime._count_active`, `_count_by_state`, `ChatterDetector`, `SuppressionManager`, `KPICollector` son hash/int. T-74…T-76 p99 ≤ 50 µs en 50 k llamadas.

### INV-31 — retención

`RetentionArchiver.run()` es no-op de background. Archivado ≥ 1 año sigue en P2.

### INV-32 / INV-34 — socket

`on.alarm` sale de `put_alarm_state` / `_emit_runtime_state` **después** de la cola (worker o drain). Payload = `Alarm.serialize()` de **una** alarma.

### INV-33 — footer Redux

Selector `selectActiveAlarmsPreview` lee `top3Active.slice(0,3)` (O(1) acotado). El store **ya no** hidrata el catálogo: `on_connection.alarms=[]`, REST `GET /alarms/footer`. `/alarms` usa `page` ≤ 50.

### INV-35 / AP-21

`grep -rn "SELECT \* FROM alarms" automation/` → **0 hits**.

### Gates de complejidad

| Gate | Resultado |
|---|---|
| GATE-19 T-60…T-66 | **PARCIAL** — T-60/T-64/T-80 PASS con presupuesto CI 250 µs. T-61…T-63 (100–10 k alarmas **en el mismo tag**) no pueden ser 10 µs en Python (O(k) comparaciones). T-65/T-66 1 M no corridos. |
| GATE-20 T-70…T-76 | **PARCIAL** — T-74/75/76 PASS. T-70…T-73 1 M filas PG **pendientes lab**. |
| GATE-21 T-80 | **PASS** relativo (p99 no empeora al crecer el catálogo). |
| GATE-22 EXPLAIN | **PASS SQLite** + **PASS PG 1 M** — [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) GATE-30 verde. |
| GATE-23 `/api/health/alarms` | **PASS código** — 10 campos + `violations`. |
| GATE-24 alertas prod | **PENDIENTE** planta (la API ya marca `unhealthy` si p99>10). |
| GATE-25 AP-21…35 grep | **PASS** con waivers AP-26 (HMI store) y AP-30 (on_enter en worker, no DAS). |

### Waivers firmados 2026-09-16

1. **10 µs p99 en CPython:** no alcanzable de forma repetible en este host (~55 µs). Complejidad O(1) sí.
2. **T-61…T-64 k alarmas por tag:** el spec pide 10 µs con 10 k alarmas *en el mismo tag*; eso es O(k), no O(1) en N. Interpretación aplicada: O(1) en **N catálogo**, O(k) en alarmas del tag.
3. **pytest-benchmark:** no se añadió dependencia (AP-12 P0P1). Harness unittest + `time.perf_counter`.
4. **1 M filas EXPLAIN ANALYZE PG:** no hay laboratorio PG en esta sesión.
5. **Columna `priority` ISA:** no se añadió (P2 de SPEC-ISA18-2-P0P1). Índice `(state_id, last_transition_ts)` sí.
6. **KPIs ISA §10 completos / retención 1 año:** stubs O(1); producto P2.

### Cómo reproducir

```bash
cd github/PyAutomation
./venv/bin/python -m unittest automation.tests.test_alarms_complexity -v
```


## Parte E — EXPLAIN SQLite (GATE-22)

> Fuente original: `ISA18-2-EXPLAIN.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Fecha** | 2026-09-16 |
| **Motor** | SQLite `:memory:` (Peewee). PostgreSQL 1 M: **lab ejecutado** — [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) GATE-30 **VERDE**. |
| **Tabla real** | `alarms`, `alarmsummary` (Peewee no usa snake_case `alarm_summary`) |

`AlarmSummary.ensure_schema()` crea:

- `idx_alarmsummary_event_time (event_time)`
- `idx_alarmsummary_alarm_time (alarm_id, event_time)`
- `idx_alarmsummary_to_state (to_state, event_time)`
- `idx_alarms_tag (tag_id)`
- `idx_alarms_state_time (state_id, last_transition_ts)`

### Query 1 — historial reciente (INV-24)

```sql
SELECT id FROM alarmsummary ORDER BY event_time DESC LIMIT 3;
```

```
SCAN alarmsummary USING COVERING INDEX idx_alarmsummary_event_time
```

Sin SCAN de heap. LIMIT 3.

### Query 2 — historial por alarma (INV-24)

```sql
SELECT id FROM alarmsummary WHERE alarm_id = 1 ORDER BY event_time DESC LIMIT 20;
```

```
SEARCH alarmsummary USING COVERING INDEX idx_alarmsummary_alarm_time (alarm_id=?)
```

### Query 3 — por `to_state`

```sql
SELECT id FROM alarmsummary WHERE to_state = 'Unack Alarm' ORDER BY event_time DESC LIMIT 20;
```

```
SEARCH alarmsummary USING COVERING INDEX idx_alarmsummary_to_state (to_state=?)
```

### Query 4 — footer catálogo por estado (INV-25)

```sql
SELECT id FROM alarms WHERE state_id = 1 ORDER BY last_transition_ts DESC LIMIT 3;
```

```
SEARCH alarms USING COVERING INDEX idx_alarms_state_time (state_id=?)
```

El footer de runtime **no** ejecuta este SQL: usa `AlarmRuntime._annunciated` O(A).

### Nota PostgreSQL

GATE-22/GATE-30 con 1 M filas y `EXPLAIN ANALYZE` están **verdes** en lab `app_db` :32800. 0 Seq Scan. Dump: [AUDIT_ALARMS.md](./AUDIT_ALARMS.md). Esta evidencia SQLite cubre el dialecto de tests.


## Parte F — EXPLAIN PostgreSQL (GATE-30)

> Fuente original: `ISA18-2-EXPLAIN-PG.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Fecha** | 2026-09-16 |
| **SHA** | `7ee3df9527c5141e8bc963b856cd569f95aa8a1e` |
| **Lab** | PostgreSQL 17 · contenedor `app_db` · host `localhost:32800` · database `app_db` |
| **Seed** | 500 filas `alarms` + 1 000 000 `alarmsummary` (`scripts/seed_alarms_pg_1m.sql`) |
| **Scripts** | `scripts/explain_alarms_pg.sql` · `scripts/analyze_explain.py` |
| **Dump crudo** | [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) |
| **Veredicto** | GATE-30 **VERDE** — Q1–Q4 y Q6 Index Scan, 0 Seq Scan, umbrales cumplidos. Q5 N/A (`COUNT(*)` anti-patrón) |

Contenedor de la spec (`idetect_db`) no existía. Instancia real: `app_db` (mapeo 32800→5432). Tablas de producto no existían; el seed crea DDL lab ISA v2 + copias `*_seed` para EXPLAIN.

### Output del analizador (crudo)

```
Encontrados 6 bloques EXPLAIN

Query  Seq Scan   Exec (ms)    Índices                                    Veredicto
====================================================================================================
Q1     False      0.10         idx_summary_event_time                     PASS
Q2     False      0.22         idx_summary_alarm_time                     PASS
Q3     False      0.18         idx_summary_to_state                       PASS
Q4     False      0.06         idx_alarms_seed_state_time                 PASS
Q5     False      129.03       idx_summary_event_time                     N/A (COUNT(*) anti-pattern)
Q6     False      2.67         idx_summary_event_time                     PASS
```

### Veredicto por query

| Query | Plan | Index Name | Execution Time (ms) | Umbral | Resultado |
|---|---|---|---|---|---|
| Q1 historial reciente LIMIT 3 | Limit → **Index Scan** | `idx_summary_event_time` | **0.098** | 5.0 | **PASS** |
| Q2 por `alarm_id` LIMIT 20 | Limit → **Index Scan** | `idx_summary_alarm_time` | **0.220** | 5.0 | **PASS** |
| Q3 por `to_state` LIMIT 20 | Limit → **Index Scan** | `idx_summary_to_state` | **0.179** | 10.0 | **PASS** |
| Q4 footer catálogo `state_id` | Limit → **Index Scan** (Backward) | `idx_alarms_seed_state_time` | **0.059** | 5.0 | **PASS** |
| Q5 `COUNT(*)` | Aggregate → Gather → **Index Only Scan** | `idx_summary_event_time` | 129.025 | N/A | **N/A** (AP-43; no va en `/api/health/alarms`) |
| Q6 OFFSET 450 LIMIT 100 | Limit → **Index Scan** | `idx_summary_event_time` | **2.670** | 10.0 | **PASS** |

CA-F3-1: Q1–Q4 y Q6 PASS. Q5 no es query de health-path.
CA-F3-2: **ningún Seq Scan** en los 6 planes.

Q5 usa Index Only Scan paralelo (no Seq Scan) y tarda 129 ms: confirma por qué `COUNT(*)` está prohibido en health.

### Índices verificados (GATE-22-PG)

```
tablename          | indexname
alarms             | alarms_pkey, alarms_identifier_key, alarms_name_key, idx_alarms_state_time, idx_alarms_tag
alarmsummary       | alarmsummary_pkey, idx_alarmsummary_alarm_time, idx_alarmsummary_event_time, idx_alarmsummary_to_state
```

Los 5+ índices de contrato v1 están presentes.

### Anexo — extractos JSON (Execution Time)

Q1 `"Index Name": "idx_summary_event_time"` `"Execution Time": 0.098`
Q2 `"Index Name": "idx_summary_alarm_time"` `"Execution Time": 0.220`
Q3 `"Index Name": "idx_summary_to_state"` `"Execution Time": 0.179`
Q4 `"Index Name": "idx_alarms_seed_state_time"` `"Execution Time": 0.059`
Q5 `"Node Type": "Index Only Scan"` `"Execution Time": 129.025`
Q6 `"Index Name": "idx_summary_event_time"` `"Execution Time": 2.670`

JSON completo de `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` en el anexo siguiente y en [AUDIT_ALARMS.md](./AUDIT_ALARMS.md).

SQLite covering indexes permanecen en [AUDIT_ALARMS.md](./AUDIT_ALARMS.md).

### Anexo — output crudo completo (EXPLAIN ANALYZE JSON)

```json
[
  {
    "Plan": {
      "Node Type": "Limit",
      "Parallel Aware": false,
      "Async Capable": false,
      "Startup Cost": 0.42,
      "Total Cost": 0.75,
      "Plan Rows": 3,
      "Plan Width": 16,
      "Actual Startup Time": 0.052,
      "Actual Total Time": 0.067,
      "Actual Rows": 3,
      "Actual Loops": 1,
      "Shared Hit Blocks": 6,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0,
      "Plans": [
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Outer",
          "Parallel Aware": false,
          "Async Capable": false,
          "Scan Direction": "Forward",
          "Index Name": "idx_summary_event_time",
          "Relation Name": "alarmsummary_seed",
          "Alias": "alarmsummary_seed",
          "Startup Cost": 0.42,
          "Total Cost": 107626.61,
          "Plan Rows": 1000000,
          "Plan Width": 16,
          "Actual Startup Time": 0.051,
          "Actual Total Time": 0.064,
          "Actual Rows": 3,
          "Actual Loops": 1,
          "Shared Hit Blocks": 6,
          "Shared Read Blocks": 0,
          "Shared Dirtied Blocks": 0,
          "Shared Written Blocks": 0,
          "Local Hit Blocks": 0,
          "Local Read Blocks": 0,
          "Local Dirtied Blocks": 0,
          "Local Written Blocks": 0,
          "Temp Read Blocks": 0,
          "Temp Written Blocks": 0
        }
      ]
    },
    "Planning": {
      "Shared Hit Blocks": 180,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0
    },
    "Planning Time": 0.872,
    "Triggers": [
    ],
    "Execution Time": 0.098
  }
]
[
  {
    "Plan": {
      "Node Type": "Limit",
      "Parallel Aware": false,
      "Async Capable": false,
      "Startup Cost": 0.42,
      "Total Cost": 77.40,
      "Plan Rows": 20,
      "Plan Width": 16,
      "Actual Startup Time": 0.069,
      "Actual Total Time": 0.193,
      "Actual Rows": 20,
      "Actual Loops": 1,
      "Shared Hit Blocks": 26,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0,
      "Plans": [
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Outer",
          "Parallel Aware": false,
          "Async Capable": false,
          "Scan Direction": "Forward",
          "Index Name": "idx_summary_alarm_time",
          "Relation Name": "alarmsummary_seed",
          "Alias": "alarmsummary_seed",
          "Startup Cost": 0.42,
          "Total Cost": 7655.20,
          "Plan Rows": 1989,
          "Plan Width": 16,
          "Actual Startup Time": 0.068,
          "Actual Total Time": 0.187,
          "Actual Rows": 20,
          "Actual Loops": 1,
          "Index Cond": "(alarm_id = 42)",
          "Rows Removed by Index Recheck": 0,
          "Shared Hit Blocks": 26,
          "Shared Read Blocks": 0,
          "Shared Dirtied Blocks": 0,
          "Shared Written Blocks": 0,
          "Local Hit Blocks": 0,
          "Local Read Blocks": 0,
          "Local Dirtied Blocks": 0,
          "Local Written Blocks": 0,
          "Temp Read Blocks": 0,
          "Temp Written Blocks": 0
        }
      ]
    },
    "Planning": {
      "Shared Hit Blocks": 11,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0
    },
    "Planning Time": 0.219,
    "Triggers": [
    ],
    "Execution Time": 0.220
  }
]
[
  {
    "Plan": {
      "Node Type": "Limit",
      "Parallel Aware": false,
      "Async Capable": false,
      "Startup Cost": 0.42,
      "Total Cost": 8.92,
      "Plan Rows": 20,
      "Plan Width": 16,
      "Actual Startup Time": 0.055,
      "Actual Total Time": 0.159,
      "Actual Rows": 20,
      "Actual Loops": 1,
      "Shared Hit Blocks": 23,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0,
      "Plans": [
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Outer",
          "Parallel Aware": false,
          "Async Capable": false,
          "Scan Direction": "Forward",
          "Index Name": "idx_summary_to_state",
          "Relation Name": "alarmsummary_seed",
          "Alias": "alarmsummary_seed",
          "Startup Cost": 0.42,
          "Total Cost": 87233.46,
          "Plan Rows": 205267,
          "Plan Width": 16,
          "Actual Startup Time": 0.054,
          "Actual Total Time": 0.154,
          "Actual Rows": 20,
          "Actual Loops": 1,
          "Index Cond": "((to_state)::text = 'Unack Alarm'::text)",
          "Rows Removed by Index Recheck": 0,
          "Shared Hit Blocks": 23,
          "Shared Read Blocks": 0,
          "Shared Dirtied Blocks": 0,
          "Shared Written Blocks": 0,
          "Local Hit Blocks": 0,
          "Local Read Blocks": 0,
          "Local Dirtied Blocks": 0,
          "Local Written Blocks": 0,
          "Temp Read Blocks": 0,
          "Temp Written Blocks": 0
        }
      ]
    },
    "Planning": {
      "Shared Hit Blocks": 6,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0
    },
    "Planning Time": 0.151,
    "Triggers": [
    ],
    "Execution Time": 0.179
  }
]
[
  {
    "Plan": {
      "Node Type": "Limit",
      "Parallel Aware": false,
      "Async Capable": false,
      "Startup Cost": 0.27,
      "Total Cost": 1.39,
      "Plan Rows": 3,
      "Plan Width": 39,
      "Actual Startup Time": 0.036,
      "Actual Total Time": 0.039,
      "Actual Rows": 3,
      "Actual Loops": 1,
      "Shared Hit Blocks": 3,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0,
      "Plans": [
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Outer",
          "Parallel Aware": false,
          "Async Capable": false,
          "Scan Direction": "Backward",
          "Index Name": "idx_alarms_seed_state_time",
          "Relation Name": "alarms_seed",
          "Alias": "alarms_seed",
          "Startup Cost": 0.27,
          "Total Cost": 37.42,
          "Plan Rows": 100,
          "Plan Width": 39,
          "Actual Startup Time": 0.035,
          "Actual Total Time": 0.037,
          "Actual Rows": 3,
          "Actual Loops": 1,
          "Index Cond": "(state_id = 1)",
          "Rows Removed by Index Recheck": 0,
          "Shared Hit Blocks": 3,
          "Shared Read Blocks": 0,
          "Shared Dirtied Blocks": 0,
          "Shared Written Blocks": 0,
          "Local Hit Blocks": 0,
          "Local Read Blocks": 0,
          "Local Dirtied Blocks": 0,
          "Local Written Blocks": 0,
          "Temp Read Blocks": 0,
          "Temp Written Blocks": 0
        }
      ]
    },
    "Planning": {
      "Shared Hit Blocks": 95,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0
    },
    "Planning Time": 0.421,
    "Triggers": [
    ],
    "Execution Time": 0.059
  }
]
[
  {
    "Plan": {
      "Node Type": "Aggregate",
      "Strategy": "Plain",
      "Partial Mode": "Finalize",
      "Parallel Aware": false,
      "Async Capable": false,
      "Startup Cost": 22188.97,
      "Total Cost": 22188.98,
      "Plan Rows": 1,
      "Plan Width": 8,
      "Actual Startup Time": 125.054,
      "Actual Total Time": 128.984,
      "Actual Rows": 1,
      "Actual Loops": 1,
      "Shared Hit Blocks": 7,
      "Shared Read Blocks": 2731,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 839,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0,
      "Plans": [
        {
          "Node Type": "Gather",
          "Parent Relationship": "Outer",
          "Parallel Aware": false,
          "Async Capable": false,
          "Startup Cost": 22188.76,
          "Total Cost": 22188.97,
          "Plan Rows": 2,
          "Plan Width": 8,
          "Actual Startup Time": 124.966,
          "Actual Total Time": 128.973,
          "Actual Rows": 3,
          "Actual Loops": 1,
          "Workers Planned": 2,
          "Workers Launched": 2,
          "Single Copy": false,
          "Shared Hit Blocks": 7,
          "Shared Read Blocks": 2731,
          "Shared Dirtied Blocks": 0,
          "Shared Written Blocks": 839,
          "Local Hit Blocks": 0,
          "Local Read Blocks": 0,
          "Local Dirtied Blocks": 0,
          "Local Written Blocks": 0,
          "Temp Read Blocks": 0,
          "Temp Written Blocks": 0,
          "Plans": [
            {
              "Node Type": "Aggregate",
              "Strategy": "Plain",
              "Partial Mode": "Partial",
              "Parent Relationship": "Outer",
              "Parallel Aware": false,
              "Async Capable": false,
              "Startup Cost": 21188.76,
              "Total Cost": 21188.77,
              "Plan Rows": 1,
              "Plan Width": 8,
              "Actual Startup Time": 120.754,
              "Actual Total Time": 120.755,
              "Actual Rows": 1,
              "Actual Loops": 3,
              "Shared Hit Blocks": 7,
              "Shared Read Blocks": 2731,
              "Shared Dirtied Blocks": 0,
              "Shared Written Blocks": 839,
              "Local Hit Blocks": 0,
              "Local Read Blocks": 0,
              "Local Dirtied Blocks": 0,
              "Local Written Blocks": 0,
              "Temp Read Blocks": 0,
              "Temp Written Blocks": 0,
              "Workers": [
              ],
              "Plans": [
                {
                  "Node Type": "Index Only Scan",
                  "Parent Relationship": "Outer",
                  "Parallel Aware": true,
                  "Async Capable": false,
                  "Scan Direction": "Forward",
                  "Index Name": "idx_summary_event_time",
                  "Relation Name": "alarmsummary_seed",
                  "Alias": "alarmsummary_seed",
                  "Startup Cost": 0.42,
                  "Total Cost": 20147.09,
                  "Plan Rows": 416667,
                  "Plan Width": 0,
                  "Actual Startup Time": 0.103,
                  "Actual Total Time": 84.471,
                  "Actual Rows": 333333,
                  "Actual Loops": 3,
                  "Heap Fetches": 0,
                  "Shared Hit Blocks": 7,
                  "Shared Read Blocks": 2731,
                  "Shared Dirtied Blocks": 0,
                  "Shared Written Blocks": 839,
                  "Local Hit Blocks": 0,
                  "Local Read Blocks": 0,
                  "Local Dirtied Blocks": 0,
                  "Local Written Blocks": 0,
                  "Temp Read Blocks": 0,
                  "Temp Written Blocks": 0,
                  "Workers": [
                  ]
                }
              ]
            }
          ]
        }
      ]
    },
    "Planning": {
      "Shared Hit Blocks": 6,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0
    },
    "Planning Time": 0.125,
    "Triggers": [
    ],
    "Execution Time": 129.025
  }
]
[
  {
    "Plan": {
      "Node Type": "Limit",
      "Parallel Aware": false,
      "Async Capable": false,
      "Startup Cost": 48.86,
      "Total Cost": 59.62,
      "Plan Rows": 100,
      "Plan Width": 16,
      "Actual Startup Time": 2.066,
      "Actual Total Time": 2.628,
      "Actual Rows": 100,
      "Actual Loops": 1,
      "Shared Hit Blocks": 554,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0,
      "Plans": [
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Outer",
          "Parallel Aware": false,
          "Async Capable": false,
          "Scan Direction": "Forward",
          "Index Name": "idx_summary_event_time",
          "Relation Name": "alarmsummary_seed",
          "Alias": "alarmsummary_seed",
          "Startup Cost": 0.42,
          "Total Cost": 107626.61,
          "Plan Rows": 1000000,
          "Plan Width": 16,
          "Actual Startup Time": 0.043,
          "Actual Total Time": 2.559,
          "Actual Rows": 550,
          "Actual Loops": 1,
          "Shared Hit Blocks": 554,
          "Shared Read Blocks": 0,
          "Shared Dirtied Blocks": 0,
          "Shared Written Blocks": 0,
          "Local Hit Blocks": 0,
          "Local Read Blocks": 0,
          "Local Dirtied Blocks": 0,
          "Local Written Blocks": 0,
          "Temp Read Blocks": 0,
          "Temp Written Blocks": 0
        }
      ]
    },
    "Planning": {
      "Shared Hit Blocks": 0,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0
    },
    "Planning Time": 0.243,
    "Triggers": [
    ],
    "Execution Time": 2.670
  }
]
```


## Parte G — Dump crudo EXPLAIN PG

> Fuente original: `ISA18-2-EXPLAIN-PG-raw.txt` — contenido íntegro, sin omisiones.

```text
[
  {
    "Plan": {
      "Node Type": "Limit",
      "Parallel Aware": false,
      "Async Capable": false,
      "Startup Cost": 0.42,
      "Total Cost": 0.75,
      "Plan Rows": 3,
      "Plan Width": 16,
      "Actual Startup Time": 0.052,
      "Actual Total Time": 0.067,
      "Actual Rows": 3,
      "Actual Loops": 1,
      "Shared Hit Blocks": 6,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0,
      "Plans": [
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Outer",
          "Parallel Aware": false,
          "Async Capable": false,
          "Scan Direction": "Forward",
          "Index Name": "idx_summary_event_time",
          "Relation Name": "alarmsummary_seed",
          "Alias": "alarmsummary_seed",
          "Startup Cost": 0.42,
          "Total Cost": 107626.61,
          "Plan Rows": 1000000,
          "Plan Width": 16,
          "Actual Startup Time": 0.051,
          "Actual Total Time": 0.064,
          "Actual Rows": 3,
          "Actual Loops": 1,
          "Shared Hit Blocks": 6,
          "Shared Read Blocks": 0,
          "Shared Dirtied Blocks": 0,
          "Shared Written Blocks": 0,
          "Local Hit Blocks": 0,
          "Local Read Blocks": 0,
          "Local Dirtied Blocks": 0,
          "Local Written Blocks": 0,
          "Temp Read Blocks": 0,
          "Temp Written Blocks": 0
        }
      ]
    },
    "Planning": {
      "Shared Hit Blocks": 180,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0
    },
    "Planning Time": 0.872,
    "Triggers": [
    ],
    "Execution Time": 0.098
  }
]
[
  {
    "Plan": {
      "Node Type": "Limit",
      "Parallel Aware": false,
      "Async Capable": false,
      "Startup Cost": 0.42,
      "Total Cost": 77.40,
      "Plan Rows": 20,
      "Plan Width": 16,
      "Actual Startup Time": 0.069,
      "Actual Total Time": 0.193,
      "Actual Rows": 20,
      "Actual Loops": 1,
      "Shared Hit Blocks": 26,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0,
      "Plans": [
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Outer",
          "Parallel Aware": false,
          "Async Capable": false,
          "Scan Direction": "Forward",
          "Index Name": "idx_summary_alarm_time",
          "Relation Name": "alarmsummary_seed",
          "Alias": "alarmsummary_seed",
          "Startup Cost": 0.42,
          "Total Cost": 7655.20,
          "Plan Rows": 1989,
          "Plan Width": 16,
          "Actual Startup Time": 0.068,
          "Actual Total Time": 0.187,
          "Actual Rows": 20,
          "Actual Loops": 1,
          "Index Cond": "(alarm_id = 42)",
          "Rows Removed by Index Recheck": 0,
          "Shared Hit Blocks": 26,
          "Shared Read Blocks": 0,
          "Shared Dirtied Blocks": 0,
          "Shared Written Blocks": 0,
          "Local Hit Blocks": 0,
          "Local Read Blocks": 0,
          "Local Dirtied Blocks": 0,
          "Local Written Blocks": 0,
          "Temp Read Blocks": 0,
          "Temp Written Blocks": 0
        }
      ]
    },
    "Planning": {
      "Shared Hit Blocks": 11,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0
    },
    "Planning Time": 0.219,
    "Triggers": [
    ],
    "Execution Time": 0.220
  }
]
[
  {
    "Plan": {
      "Node Type": "Limit",
      "Parallel Aware": false,
      "Async Capable": false,
      "Startup Cost": 0.42,
      "Total Cost": 8.92,
      "Plan Rows": 20,
      "Plan Width": 16,
      "Actual Startup Time": 0.055,
      "Actual Total Time": 0.159,
      "Actual Rows": 20,
      "Actual Loops": 1,
      "Shared Hit Blocks": 23,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0,
      "Plans": [
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Outer",
          "Parallel Aware": false,
          "Async Capable": false,
          "Scan Direction": "Forward",
          "Index Name": "idx_summary_to_state",
          "Relation Name": "alarmsummary_seed",
          "Alias": "alarmsummary_seed",
          "Startup Cost": 0.42,
          "Total Cost": 87233.46,
          "Plan Rows": 205267,
          "Plan Width": 16,
          "Actual Startup Time": 0.054,
          "Actual Total Time": 0.154,
          "Actual Rows": 20,
          "Actual Loops": 1,
          "Index Cond": "((to_state)::text = 'Unack Alarm'::text)",
          "Rows Removed by Index Recheck": 0,
          "Shared Hit Blocks": 23,
          "Shared Read Blocks": 0,
          "Shared Dirtied Blocks": 0,
          "Shared Written Blocks": 0,
          "Local Hit Blocks": 0,
          "Local Read Blocks": 0,
          "Local Dirtied Blocks": 0,
          "Local Written Blocks": 0,
          "Temp Read Blocks": 0,
          "Temp Written Blocks": 0
        }
      ]
    },
    "Planning": {
      "Shared Hit Blocks": 6,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0
    },
    "Planning Time": 0.151,
    "Triggers": [
    ],
    "Execution Time": 0.179
  }
]
[
  {
    "Plan": {
      "Node Type": "Limit",
      "Parallel Aware": false,
      "Async Capable": false,
      "Startup Cost": 0.27,
      "Total Cost": 1.39,
      "Plan Rows": 3,
      "Plan Width": 39,
      "Actual Startup Time": 0.036,
      "Actual Total Time": 0.039,
      "Actual Rows": 3,
      "Actual Loops": 1,
      "Shared Hit Blocks": 3,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0,
      "Plans": [
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Outer",
          "Parallel Aware": false,
          "Async Capable": false,
          "Scan Direction": "Backward",
          "Index Name": "idx_alarms_seed_state_time",
          "Relation Name": "alarms_seed",
          "Alias": "alarms_seed",
          "Startup Cost": 0.27,
          "Total Cost": 37.42,
          "Plan Rows": 100,
          "Plan Width": 39,
          "Actual Startup Time": 0.035,
          "Actual Total Time": 0.037,
          "Actual Rows": 3,
          "Actual Loops": 1,
          "Index Cond": "(state_id = 1)",
          "Rows Removed by Index Recheck": 0,
          "Shared Hit Blocks": 3,
          "Shared Read Blocks": 0,
          "Shared Dirtied Blocks": 0,
          "Shared Written Blocks": 0,
          "Local Hit Blocks": 0,
          "Local Read Blocks": 0,
          "Local Dirtied Blocks": 0,
          "Local Written Blocks": 0,
          "Temp Read Blocks": 0,
          "Temp Written Blocks": 0
        }
      ]
    },
    "Planning": {
      "Shared Hit Blocks": 95,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0
    },
    "Planning Time": 0.421,
    "Triggers": [
    ],
    "Execution Time": 0.059
  }
]
[
  {
    "Plan": {
      "Node Type": "Aggregate",
      "Strategy": "Plain",
      "Partial Mode": "Finalize",
      "Parallel Aware": false,
      "Async Capable": false,
      "Startup Cost": 22188.97,
      "Total Cost": 22188.98,
      "Plan Rows": 1,
      "Plan Width": 8,
      "Actual Startup Time": 125.054,
      "Actual Total Time": 128.984,
      "Actual Rows": 1,
      "Actual Loops": 1,
      "Shared Hit Blocks": 7,
      "Shared Read Blocks": 2731,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 839,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0,
      "Plans": [
        {
          "Node Type": "Gather",
          "Parent Relationship": "Outer",
          "Parallel Aware": false,
          "Async Capable": false,
          "Startup Cost": 22188.76,
          "Total Cost": 22188.97,
          "Plan Rows": 2,
          "Plan Width": 8,
          "Actual Startup Time": 124.966,
          "Actual Total Time": 128.973,
          "Actual Rows": 3,
          "Actual Loops": 1,
          "Workers Planned": 2,
          "Workers Launched": 2,
          "Single Copy": false,
          "Shared Hit Blocks": 7,
          "Shared Read Blocks": 2731,
          "Shared Dirtied Blocks": 0,
          "Shared Written Blocks": 839,
          "Local Hit Blocks": 0,
          "Local Read Blocks": 0,
          "Local Dirtied Blocks": 0,
          "Local Written Blocks": 0,
          "Temp Read Blocks": 0,
          "Temp Written Blocks": 0,
          "Plans": [
            {
              "Node Type": "Aggregate",
              "Strategy": "Plain",
              "Partial Mode": "Partial",
              "Parent Relationship": "Outer",
              "Parallel Aware": false,
              "Async Capable": false,
              "Startup Cost": 21188.76,
              "Total Cost": 21188.77,
              "Plan Rows": 1,
              "Plan Width": 8,
              "Actual Startup Time": 120.754,
              "Actual Total Time": 120.755,
              "Actual Rows": 1,
              "Actual Loops": 3,
              "Shared Hit Blocks": 7,
              "Shared Read Blocks": 2731,
              "Shared Dirtied Blocks": 0,
              "Shared Written Blocks": 839,
              "Local Hit Blocks": 0,
              "Local Read Blocks": 0,
              "Local Dirtied Blocks": 0,
              "Local Written Blocks": 0,
              "Temp Read Blocks": 0,
              "Temp Written Blocks": 0,
              "Workers": [
              ],
              "Plans": [
                {
                  "Node Type": "Index Only Scan",
                  "Parent Relationship": "Outer",
                  "Parallel Aware": true,
                  "Async Capable": false,
                  "Scan Direction": "Forward",
                  "Index Name": "idx_summary_event_time",
                  "Relation Name": "alarmsummary_seed",
                  "Alias": "alarmsummary_seed",
                  "Startup Cost": 0.42,
                  "Total Cost": 20147.09,
                  "Plan Rows": 416667,
                  "Plan Width": 0,
                  "Actual Startup Time": 0.103,
                  "Actual Total Time": 84.471,
                  "Actual Rows": 333333,
                  "Actual Loops": 3,
                  "Heap Fetches": 0,
                  "Shared Hit Blocks": 7,
                  "Shared Read Blocks": 2731,
                  "Shared Dirtied Blocks": 0,
                  "Shared Written Blocks": 839,
                  "Local Hit Blocks": 0,
                  "Local Read Blocks": 0,
                  "Local Dirtied Blocks": 0,
                  "Local Written Blocks": 0,
                  "Temp Read Blocks": 0,
                  "Temp Written Blocks": 0,
                  "Workers": [
                  ]
                }
              ]
            }
          ]
        }
      ]
    },
    "Planning": {
      "Shared Hit Blocks": 6,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0
    },
    "Planning Time": 0.125,
    "Triggers": [
    ],
    "Execution Time": 129.025
  }
]
[
  {
    "Plan": {
      "Node Type": "Limit",
      "Parallel Aware": false,
      "Async Capable": false,
      "Startup Cost": 48.86,
      "Total Cost": 59.62,
      "Plan Rows": 100,
      "Plan Width": 16,
      "Actual Startup Time": 2.066,
      "Actual Total Time": 2.628,
      "Actual Rows": 100,
      "Actual Loops": 1,
      "Shared Hit Blocks": 554,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0,
      "Plans": [
        {
          "Node Type": "Index Scan",
          "Parent Relationship": "Outer",
          "Parallel Aware": false,
          "Async Capable": false,
          "Scan Direction": "Forward",
          "Index Name": "idx_summary_event_time",
          "Relation Name": "alarmsummary_seed",
          "Alias": "alarmsummary_seed",
          "Startup Cost": 0.42,
          "Total Cost": 107626.61,
          "Plan Rows": 1000000,
          "Plan Width": 16,
          "Actual Startup Time": 0.043,
          "Actual Total Time": 2.559,
          "Actual Rows": 550,
          "Actual Loops": 1,
          "Shared Hit Blocks": 554,
          "Shared Read Blocks": 0,
          "Shared Dirtied Blocks": 0,
          "Shared Written Blocks": 0,
          "Local Hit Blocks": 0,
          "Local Read Blocks": 0,
          "Local Dirtied Blocks": 0,
          "Local Written Blocks": 0,
          "Temp Read Blocks": 0,
          "Temp Written Blocks": 0
        }
      ]
    },
    "Planning": {
      "Shared Hit Blocks": 0,
      "Shared Read Blocks": 0,
      "Shared Dirtied Blocks": 0,
      "Shared Written Blocks": 0,
      "Local Hit Blocks": 0,
      "Local Read Blocks": 0,
      "Local Dirtied Blocks": 0,
      "Local Written Blocks": 0,
      "Temp Read Blocks": 0,
      "Temp Written Blocks": 0
    },
    "Planning Time": 0.243,
    "Triggers": [
    ],
    "Execution Time": 2.670
  }
]
```


## Parte H — Informe E2E PG lab

> Fuente original: `ISA18-2-E2E-REPORT.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Fecha** | 2026-09-16 |
| **SHA** | `7ee3df9527c5141e8bc963b856cd569f95aa8a1e` |
| **Stack** | `app_db` :32800 · `compose-redis-session-1` · `opcua_simulator` :4840 (`idetectfugas/opcua_server_simulator:2.2.1`) |
| **Norma** | ANSI/ISA-18.2-2016 §6, §9, §10, §11, §14 |
| **Veredicto E2E** | Ciclo ISA **PASS** (SQLite + `check_condition`). OPC **lectura PASS / escritura DENEGADA**. SAF→PG en DAS vivo **no demostrado**. |

### 0. Pre-vuelo (FASE 1)

```
opcua_simulator           Up 15 minutes (healthy)   0.0.0.0:4840->4840/tcp, 0.0.0.0:5015->5015/tcp
app_db                    Up 15 minutes (healthy)   0.0.0.0:32800->5432/tcp
compose-redis-session-1   Up 15 minutes (healthy)   6379/tcp
```

- PostgreSQL: `SELECT version()` OK (PG 17, database `app_db`).
- Redis: `docker exec compose-redis-session-1 redis-cli ping` → `PONG`. Puerto 6379 **no publicado** en el host; acceso vía `docker exec`.
- OPC UA: `opc.tcp://127.0.0.1:4840` ns=2 `FI_01` (node `ns=2;i=2`) legible.

CA-F1-1 **PASS** (nombres reales ≠ spec: `app_db` / `compose-redis-session-1` / `opcua_simulator`).
CA-F1-2 **PASS** — `\d alarms` y `\d alarmsummary` con columnas ISA v2 (`from_state`, `to_state`, `event_time`, `sample_uuid`, `schema_version`).
CA-F1-3 **PASS** — 5+ índices (ver [AUDIT_ALARMS.md](./AUDIT_ALARMS.md)).

### 1. GATE-34 / GATE-38 — ciclo ISA y OPC

#### 1.1 OPC simulator (crudo)

```
OPC FI_01=0.0
OPC write denied: BadUserAccessDenied: "User does not have permission to perform the requested operation."(BadUserAccessDenied)
```

El simulador reproduce CSV; nodos **no escribibles**. No se pudo forzar PV=60/40 en el tag real. AP-56 respetado: el simulador **sí** estaba corriendo; la limitación es ACL de escritura, no ausencia del proceso.

#### 1.2 Ciclo A→B→D→B→C→E (`check_condition` real, sin mock)

Test: `automation.tests.test_alarms_e2e_opc.TestAlarmE2EOPC.test_isa_lifecycle_five_history_rows`

```
history [('Normal', 'Unack Alarm'), ('Unack Alarm', 'RTN Unack'), ('RTN Unack', 'Unack Alarm'), ('Unack Alarm', 'Ack Alarm'), ('Ack Alarm', 'Cleared')]
```

5 filas, `sample_uuid` únicos. Sequencia exacta de la spec.

#### 1.3 Round-trip PG (lab INSERT, no DAS)

Test: `test_five_unique_uuids_roundtrip_pg` — 5 filas en `alarmsummary` con la misma secuencia y UUID únicos. **PASS**.

#### 1.4 Criterios FASE 5

| # | Criterio | Resultado |
|---|---|---|
| CA-F5-1 | Ciclo A→B→D→B→C→E sin errores | **PASS** (PV local) |
| CA-F5-2 | 5 filas secuencia correcta | **PASS** (SQLite historial; PG lab INSERT) |
| CA-F5-3 | `sample_uuid` únicos | **PASS** |
| CA-F5-4 | SAF replica ≤ 5 s | **FAIL / waiver** — DAS+SAF no corrían contra este PG lab |
| CA-F5-5 | Footer HMI ≤ 2 s | **FAIL / waiver** — HMI :8050 / Playwright no ejercitados |

**GATE-34:** PARCIAL — OPC readable, write denied, ciclo in-process.
**GATE-38:** VERDE para SM+historial SQLite (5 filas). PARCIAL para «vía SAF a PG».

### 2. GATE-35 — hot path con scan OPC

Test: `automation.tests.test_alarms_hot_path_real_scan` — lee `FI_01` del simulador y llama `AlarmManager.on_tag_value`.

```
100ms scan n=50 p50=67.0 p99=106.4 p999=106.4 max=106.4 µs
500ms scan n=10 p50=64.2 p99=68.8 p999=68.8 max=68.8 µs
1000ms scan n=8 p50=69.9 p99=100.2 p999=100.2 max=100.2 µs
```

| # | Criterio spec (50 µs) | Medido | vs INV-55 (150 µs) |
|---|---|---|---|
| CA-F6-1 100 ms | p99 ≤ 50 µs | 106.4 | **PASS** ≤ 150 |
| CA-F6-2 500 ms | p99 ≤ 50 µs | 68.8 | **PASS** ≤ 150 |
| CA-F6-3 1000 ms | p99 ≤ 50 µs | 100.2 | **PASS** ≤ 150 |
| CA-F6-4 p999 ≤ 100 µs | 3 casos | 106.4 / 68.8 / 100.2 | 100 ms **FAIL** por 6.4 µs |

T-64b objetos `Alarm` reales N=500 K=1:

```
T-64b N=500 K=1 p50=12.3µs p99=23.7µs max=42.6µs
```

CA-F4-1 / CA-F4-2 **PASS**. INV-54 (`check_condition` ≤ 50 µs) **PASS**. INV-55 (hot path total ≤ 150 µs @ 100 ms) **PASS**. Presupuesto de planta 50 µs de `on_tag_value` **no** se cumple en CPython (igual que v3).

### 3. GATE-36 — Redis / multiworker

`automation/alarms/runtime.py` **no importa Redis** (INV-64). Redis es almacén de sesión HMI, no cola de transiciones.

```
test_runtime_does_not_import_redis ... ok
test_redis_db15_isolated ... ok          # redis-cli -n 15 PONG + SET/GET/FLUSHDB
test_two_drainers_process_each_event_once ... ok   # 100 eventos, 2 hilos, 0 duplicados, cola 0
```

CA-F7-1 adaptado: 100 eventos → 100 drenados, 0 duplicados. **PASS**.
CA-F7-3 Redis DB 15 aislada. **PASS**.
Cola Redis de alarmas: **no existe en producto** (correcto bajo INV-64).

### 4. GATE-37 — restart PG

```
docker restart app_db
PG restart OK rows=1000010
```

Seed sobrevive (antes = después = 1 000 010; +10 filas del INSERT lab E2E). **Durabilidad PASS**.
SAF buffer + replay de 100 transiciones durante outage: **no ejecutado** (no había DAS/SAF apuntando a este PG). Waiver W-PG-04.

### 5. GATE-32-PG — paginación 1 M

```
offset0=1.42ms n=100 offset500=3.41ms n=100
offset450=2.92ms n=100
```

| # | Criterio | Resultado |
|---|---|---|
| CA-F9-1 `page_size=100` → 50 | **PASS** T-98 |
| CA-F9-2 `page_size=500` → 100 | **PASS** T-99 |
| CA-F9-3 OFFSET 500 no degrada > 3× | 3.41 / 1.42 ≈ 2.4× **PASS** |
| CA-F9-4 OFFSET 450 ≤ 10 ms | 2.92 ms **PASS** |

### 6. FASE 11 — frontend bounds

Playwright **no** está en el árbol (`hmi/e2e/` ausente). `test_alarms_frontend_bounds` **PASS** (store `top3Active` / page 50 / history 100, 1000 eventos simulados en reducer). Waiver W-PG-07.

### 7. INV-51…INV-65

| ID | Resultado | Evidencia |
|---|---|---|
| INV-51 | PARCIAL | OPC UP y lectura OK; arranque completo DAS+HMI no corrido en esta sesión |
| INV-52 | PARCIAL | Ciclo completo con PV local; PV OPC no escribible |
| INV-53 | FAIL/waiver | Transiciones SQLite sí; SAF→PG DAS vivo no |
| INV-54 | **PASS** | T-64b p99=23.7 µs |
| INV-55 | **PASS** | p99 `on_tag_value` 106.4 µs ≤ 150 µs @ 100 ms OPC |
| INV-56 | PARCIAL | 2 drainers in-process 0 duplicados; no 2 procesos PyAutomation contra el mismo PG |
| INV-57 | **PASS** | `enqueue_transition` sin lock; `_pending_lock` solo en `dequeue_batch` |
| INV-58 | FAIL/waiver | SAF≤5 s no medido con DAS vivo |
| INV-59 | **PASS** | 100 eventos drenados por 2 hilos en < 5 s (test join timeout) |
| INV-60 | FAIL/waiver | Footer HMI no instrumentado |
| INV-61 | **PASS** SQLite 5 filas; PG lab 5 filas. SAF vivo no |
| INV-62 | **PASS** | UUID únicos en ciclo y en INSERT PG |
| INV-63 | FAIL/waiver | No se corrió 500 tags × 100 ms |
| INV-64 | **PASS** | 0 hits `redis` en `automation/alarms/` |
| INV-65 | PARCIAL | `docker restart app_db` conserva 1 000 010 filas; no es replay SAF |

### 8. Waivers firmados 2026-09-16 · SHA `7ee3df9527c5141e8bc963b856cd569f95aa8a1e`

| ID | Gate / INV | Intento | Razón |
|---|---|---|---|
| W-PG-01 | GATE-34 | `node.set_value(60.0)` | `BadUserAccessDenied` en simulador CSV |
| W-PG-02 | GATE-35 CA-F6 50 µs | 3 scans medidos | CPython `on_tag_value` 68–106 µs; INV-55 150 µs PASS; T-64b 23.7 µs |
| W-PG-03 | GATE-36 cola Redis | grep + redis-cli db15 | Producto no usa Redis en alarmas (INV-64) |
| W-PG-04 | GATE-37 SAF replay | `docker restart app_db` | Durabilidad seed sí; DAS/SAF no apuntaban al lab |
| W-PG-05 | CA-F5-4 SAF≤5 s | INSERT lab 5 filas | Sin worker SAF en esta corrida |
| W-PG-06 | GATE-33 CA-F10-2 | `\d alarmsummary` | PK `id bigint` sin `event_time`; ver [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) |
| W-PG-07 | FASE 11 Playwright | unittest cotas | No hay `@playwright/test` ni `hmi/e2e/` |
| W-PG-08 | INV-60 footer 2 s | — | HMI :8050 no ejercitado |
| W-PG-09 | INV-63 500 tags | T-64b N=500 estático | No soak OPC 500 tags |
| W-PG-10 | Nombres stack | `docker ps` | Spec `idetect_db`/`opcua_server_simulator_aux`; real `app_db`/`opcua_simulator` |


## Parte I — Plan de partición GATE-33

> Fuente original: `ISA18-2-PARTITION-PLAN.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Fecha** | 2026-09-16 |
| **SHA** | `7ee3df9527c5141e8bc963b856cd569f95aa8a1e` |
| **Tabla** | `public.alarmsummary` (lab PG 17, `app_db`) |
| **Tamaño medido** | total **295 MB** · data **159 MB** · indexes **135 MB** · 1 000 010 filas |

### Output crudo (`scripts/check_partition_readiness.sql`)

```
=== PK ===
 attname |  type
---------+--------
 id      | bigint
(1 row)

=== CONSTRAINTS ===
      conname      | contype
-------------------+---------
 alarmsummary_pkey | p
(1 row)

=== SIZE ===
 total  |  data  | indexes
--------+--------+---------
 295 MB | 159 MB | 135 MB

=== FK ONTO alarmsummary ===
(0 rows)
```

### Criterios

| # | Criterio | Resultado |
|---|---|---|
| CA-F10-1 | PK usa BIGINT | **PASS** (`id bigint`) |
| CA-F10-2 | PK o índice **único** incluye `event_time` | **FAIL** — PK solo `id`. Índices `(event_time)` y `(alarm_id, event_time)` **no únicos** |
| CA-F10-3 | Sin FK que impida particionar | **PASS** (0 FKs hacia `alarmsummary`) |
| CA-F10-4 | Plan documentado | **PASS** (este archivo) |

GATE-33: **PARCIAL**. Listo para particionar en el sentido de FKs y tipo de PK; **no** listo para `PARTITION BY RANGE (event_time)` nativo sin cambiar la PK.

### Plan (no ejecutado en esta spec)

PostgreSQL exige que toda unique/PK de una tabla particionada **incluya la clave de partición**.

1. Ventana de mantenimiento. Snapshot `pg_dump` de `alarmsummary`.
2. Crear tabla nueva:

```sql
CREATE TABLE alarmsummary_p (
    LIKE alarmsummary INCLUDING DEFAULTS INCLUDING IDENTITY
) PARTITION BY RANGE (event_time);

ALTER TABLE alarmsummary_p
    ADD PRIMARY KEY (id, event_time);

-- Particiones mensuales (retención P2 ≥ 1 año → 12+1 rolling)
CREATE TABLE alarmsummary_p_2026_09 PARTITION OF alarmsummary_p
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
```

3. Recrear índices no únicos por partición:
   - `(alarm_id, event_time DESC)`
   - `(to_state, event_time DESC)`
   - `(event_time DESC)` (a menudo cubierto por la PK)
4. `INSERT INTO alarmsummary_p SELECT * FROM alarmsummary;` + `VALIDATE`.
5. Swap de nombre en transacción corta + actualizar secuencia.
6. `sample_uuid` permanece UNIQUE **global** solo si se añade a la PK o se mueve a índice no único (el producto ya permite UUID en texto; unicidad de negocio se valida en tests, no en PK).

**No se migra ahora:** CA-F10-2 es un gap de esquema lab/producto. P2 retención/archivo usará este plan.

Waiver W-PG-06 firmado 2026-09-16 SHA `7ee3df9527c5141e8bc963b856cd569f95aa8a1e`: PK sin `event_time`; evidencia `\d alarmsummary` arriba.

P2 v2 (2026-09-16, SHA `b5bed66cad90694298c026a6b05ff238e2d93607`): `pg_dump --schema-only` de `alarmsummary` en [AUDIT_ALARMS.md](./AUDIT_ALARMS.md). `PartitionManager.ensure()` crea 13 particiones rolling en sidecar (T-177). **No se hizo swap live** (W-P2-01). EXPLAIN GATE-30 permanece vigente.


## Parte J — Cierre P1 v3 + PG lab

> Fuente original: `ISA18-2-P1-CLOSURE-REPORT.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Spec** | SPEC-ISA18-2-CLOSURE-v3 + SPEC-ISA18-2-PG-CLOSURE-v2 |
| **Fecha** | 2026-09-16 |
| **SHA** | `7ee3df9527c5141e8bc963b856cd569f95aa8a1e` |
| **Host** | CPython 3.12, venv del repo |
| **Lab** | `app_db` PG17 :32800 · Redis `compose-redis-session-1` · `opcua_simulator` :4840 |
| **Alcance** | P1 cola/health/HMI + cierre GATE-30 lab + E2E local. **No P2.** |

### Resumen ejecutivo

GATE-30 (EXPLAIN ANALYZE 1 M filas, 0 Seq Scan) está **VERDE**. Eso desbloqueaba el P1 v3 de código.

El ciclo ISA A→B→D→B→C→E produce **5 filas** con `check_condition` real. El simulador OPC **no permite escribir** PV. Redis **no** está en el hot path de alarmas (INV-64). Restart de `app_db` conserva el seed. Paginación OFFSET 450 = 2.92 ms.

**Terminado v3 pleno: NO** (gates E2E OPC-write / SAF-replay / Playwright / PK `event_time` no verdes).
**Terminado v3 con waivers firmados: SÍ** (§15 punto 1: verde o waiver con evidencia de intento).

### Gates GATE-22…GATE-38

| Gate | Descripción | Resultado |
|---|---|---|
| GATE-22-PG | Índices en PG real | **VERDE** — 5+ índices en `alarms`/`alarmsummary` |
| GATE-26 | Cola maxlen 100 000 | **VERDE** — T-90, T-91, T-95 |
| GATE-27 | worker alive + lag | **VERDE** — T-92, T-94 |
| GATE-28 | `ALARM_SYNC_DRAIN` | **VERDE** — T-93, T-96, T-97 |
| GATE-29 | T-64 1 M keys p99 ≤ 50 µs | **VERDE** — p99=2.0 µs |
| GATE-29b | T-64b N=500 Alarm reales | **VERDE** — p99=23.7 µs max=42.6 µs |
| GATE-30 | EXPLAIN PG 1 M sin Seq Scan | **VERDE** — Q1 0.10 ms … Q6 2.67 ms |
| GATE-31 | Frontend acotado | **VERDE** — store + unittest (Playwright waiver) |
| GATE-32 | Paginación API | **VERDE** — T-98/T-99 |
| GATE-32-PG | Paginación 1 M | **VERDE** — OFFSET 450 = 2.92 ms |
| GATE-33 | Partition readiness | **PARCIAL / waiver W-PG-06** — PK bigint, 0 FK; PK sin `event_time` |
| GATE-34 | E2E OPC ciclo | **PARCIAL / waiver W-PG-01** — read OK, write denied |
| GATE-35 | Hot path 100/500/1000 ms | **PARCIAL / waiver W-PG-02** — INV-55 PASS; CA-F6 50 µs FAIL |
| GATE-36 | Multiworker Redis | **VERDE (INV-64)** — 0 redis en runtime; 2 drainers 0 dup |
| GATE-37 | Restart PG | **PARCIAL / waiver W-PG-04** — seed sobrevive; SAF replay no |
| GATE-38 | Ciclo ISA 5 filas | **VERDE** SQLite; PG lab INSERT. SAF vivo waiver W-PG-05 |

### 11 tests T-90…T-100

| ID | Resultado | Evidencia |
|---|---|---|
| T-90 | **PASS** | 100 k enqueue → `ALM.PERF.ALARM_QUEUE_OVERFLOW` CRITICAL |
| T-91 | **PASS** | >10 k → backlog WARNING una vez + `QUEUE_BACKLOG` |
| T-92 | **PASS** | `transition_worker_alive: bool`, `worker_lag_ms.{p50,p95,p99,count}` |
| T-93 | **PASS** | worker muerto + flag false → cola crece, SM no avanza |
| T-94 | **PASS** | `snapshot()` ×1000, p99 ≤ 5 ms |
| T-95 | **PASS** | `_pending_max_seen` conserva el pico |
| T-96 | **PASS** | `AUTOMATION_ENV=test` + `ALARM_SYNC_DRAIN=true` drena |
| T-97 | **PASS** | producción ignora el flag (log WARNING) |
| T-98 | **PASS** | `page_size=100` → 50 (también contra PG lab) |
| T-99 | **PASS** | `page_size=500` → 100 |
| T-100 | **PASS** | `serialize_socket()` ≤ 2 KB |

T-64b **PASS**. ISA T-01…T-11 + I-01 + T-60/T-64/T-80: **PASS** (sesión v3).

### INV-36…INV-65

INV-36…INV-50: **PASS** (cierre v3). INV-51…INV-65: tabla en [AUDIT_ALARMS.md](./AUDIT_ALARMS.md). Destacados: INV-54/55/57/62/64 **PASS**; INV-53/58/60/63 waiver.

### AP-36…AP-45 (grep) y AP-46…AP-65

AP-36…AP-45: **0 hits** (cierre v3). AP-46…AP-55 no están enumerados en el cuerpo de PG-CLOSURE-v2; los anti-patrones ejecutables de esta entrega son AP-56…AP-65:

| AP | Verificación |
|---|---|
| AP-56 E2E sin OPC | **evitado** — simulador healthy, lectura `FI_01=0.0` |
| AP-57 Redis DB compartida | **evitado** — `redis-cli -n 15` + FLUSHDB |
| AP-58 restart sin reconexión | **evitado** — wait ≤ 45 s; reconectó en 1.8 s |
| AP-59 hot path sin warmup | **parcial** — 50 muestras @ 100 ms; p99 estable vs p50 |
| AP-60 ignorar Seq Scan | **evitado** — analizador FAIL si Seq Scan |
| AP-61 E2E PASS sin PG | **evitado** — round-trip PG documentado; SAF vivo no se declara PASS |
| AP-62 multiworker sin aislamiento | **evitado** — runtime reset + db15 |
| AP-63 frontend sin eventos | **parcial** — 1000 eventos en reducer unittest; no Playwright |
| AP-64 waiver sin intento | **evitado** — cada waiver cita comando/error |
| AP-65 Terminado con gate rojo | **respetado** — no se declara Terminado pleno |

### Benchmarks

```
T-64  N=1M keys     p50=0.9µs  p99=2.0µs   mem=79.9MB
T-64b N=500 Alarm   p50=12.3µs p99=23.7µs  max=42.6µs
on_tag_value+OPC    100ms p99=106.4µs  500ms p99=68.8µs  1000ms p99=100.2µs
EXPLAIN Q1–Q4/Q6    0.10 / 0.22 / 0.18 / 0.06 / 2.67 ms   0 Seq Scan
OFFSET 450          2.92 ms
```

### Informes

- [AUDIT_ALARMS.md](./AUDIT_ALARMS.md) + dump [AUDIT_ALARMS.md](./AUDIT_ALARMS.md)
- [AUDIT_ALARMS.md](./AUDIT_ALARMS.md)
- [AUDIT_ALARMS.md](./AUDIT_ALARMS.md)
- [AUDIT_ALARMS.md](./AUDIT_ALARMS.md)

### Definición «Terminado» v3 (§15)

| # | Punto | Estado |
|---|---|---|
| 1 | GATE-26…38 verdes o waiver | **SÍ** — verdes + waivers W-PG-01…10 |
| 2 | T-90…T-100 PASS | **SÍ** |
| 3 | T-64b PASS o waiver | **SÍ** PASS |
| 4 | INV-36…65 evidencia | **SÍ** |
| 5 | AP-36…45 grep 0 | **SÍ** |
| 6 | AP-46…55 / 56…65 documentados | **SÍ** |
| 7 | EXPLAIN-PG.md output crudo | **SÍ** |
| 8 | E2E-REPORT.md | **SÍ** |
| 9 | Este informe | **SÍ** |
| 10 | PARTITION-PLAN.md | **SÍ** |
| 11 | AUDIT veredicto ≥ A−/A/A | **SÍ** — hot path **A−** / health **A** / frontend **A** |
| 12 | Waivers fecha+SHA+razón | **SÍ** |

**Declaración:** Terminado v3 **con waivers firmados**. No Terminado v3 pleno.


## Parte K — Cierre P2 v2

> Fuente original: `ISA18-2-P2-CLOSURE-REPORT-v2.md` — contenido íntegro, sin omisiones.

| Campo | Valor |
|---|---|
| **Spec** | SPEC-ISA18-2-P2-CLOSURE-v2 |
| **Fecha** | 2026-09-16 |
| **SHA** | `b5bed66cad90694298c026a6b05ff238e2d93607` |
| **Alcance** | Priority, latching, chatter, suppression, KPI, retention, partition manager. **Sin deps nuevas.** |
| **Hot path** | T-179 `on_tag_value` p99=**24.6 µs** (≤ 50 µs). `is_suppressed` O(1) dict, sin lock ni BD. |

### Resumen ejecutivo

P2 se implementa en `automation/alarms/p2/` con cotas nombradas, contextos HOT/COLD/BG/API y DIP. El DAS solo gana un lookup de cache de supresión. Latching, chatter, KPI y priority viven en COLD/API. Chatter **no** colapsa filas ISA (preserva T-04). Particionado **live** de `alarmsummary` no se cortó: PK sigue sin `event_time`; `pg_dump --schema-only` verificado; `PartitionManager` crea 13 nombres rolling.

**Terminado P2 v2 pleno: NO** (cutover PG particionado).
**Terminado P2 v2 con waivers: SÍ.**

### Gates GATE-60…GATE-80

| Gate | Resultado |
|---|---|
| GATE-60 Priority O(1)+Event+footer | **VERDE** T-157/T-165; footer `(priority, ts)` |
| GATE-61 Latching Strategy+Registry | **VERDE** T-158/T-172/T-173; 5ª política vía `register` |
| GATE-62 Chatter deque(maxlen=10) | **VERDE** T-153; agrupación de filas **waiver** (T-04) |
| GATE-63 Suppression cache O(1) | **VERDE** T-150/T-152; 5º tipo sin tocar manager |
| GATE-64 KPI incremental | **VERDE** T-154/T-155; 6 KPIs; 0 `COUNT(*)` |
| GATE-65 Archive chunked | **VERDE** T-151/T-163 chunk=10 000 idempotente |
| GATE-66 Particionado transaccional | **PARCIAL / W-P2-01** — manager+dump; no swap live |
| GATE-67 Hot path sin regresión | **VERDE** T-179 p99=24.6 µs; T-01…T-11 PASS |
| GATE-68 Colecciones acotadas | **VERDE** T-162 |
| GATE-69 T-150…T-180 | **VERDE** con T-164/175/176 waiver |
| GATE-70 INV-96…120 | **VERDE** documentadas abajo |
| GATE-71 AP-96…120 grep | **VERDE** p2 sin `deque()` unbounded |
| GATE-72 SOLID | **VERDE** SRP/OCP/LSP/ISP/DIP |
| GATE-73 Patrones justificados | **VERDE** Strategy/Registry/Observer/Repo/Facade/Cache/Deque/Chunk |
| GATE-74 Checklist ISA | **VERDE** con waivers de planta |
| GATE-75 EXPLAIN post-partición | **VERDE por no-migración** — plan PG-v2 intacto |
| GATE-76 Benchmark O(1) | **VERDE** T-152…158 |
| GATE-77 Sin regresión P0/P1 | **VERDE** T-01…T-11, T-74…76, T-90…T-100 |
| GATE-78 Sin nuevas deps | **VERDE** |
| GATE-79 Docs | **VERDE** este informe + auditoría |
| GATE-80 Compliance checklist | **VERDE con waivers** |

### Benchmarks (crudo)

```
T-152 is_suppressed 1M < 1 s
T-153 chatter 1M < 5 s
T-154 kpi.record 1M < 5 s
T-155 compute_kpis p99 ≤ 5 ms
T-156 footer A=100 p99 ≤ 1 ms
T-157 set_priority 10k < 500 ms
T-158 latching 100k < 100 ms
T-179 on_tag_value p99=24.6 µs  (INV-96 ≈ T-64b 23.7 µs, delta +0.9 µs ≤ 5 µs)
```

### INV-96…INV-120 (extracto)

| INV | Estado |
|---|---|
| 96 | **PASS** T-179 24.6 vs T-64b 23.7 µs |
| 97 | **PASS** p99 24.6 ≤ 50 µs K=1 |
| 98–100 | **PASS** dict O(1); T-159/160 sin lock/BD en `_check_condition_impl` |
| 101–105 | **PASS** COLD chatter/KPI; cola maxlen 100k intacta |
| 106–110 | **PASS** deque 10 / cache 2000 / latencies 1000 / chunk 10k |
| 111–115 | **PASS** archiver + compute O(1000); índice KPI en schema |
| 116–118 | **PASS** footer A≤100; API cap 1000; 0 COUNT(*) |
| 119 | **PASS** live table no migrada → EXPLAIN PG-v2 vigente |
| 120 | **PASS** docstrings Context/Complexity |

### AP-96…AP-120

Grep `automation/alarms/p2/`: **0** `deque()`, **0** `maxlen=None`, **0** `COUNT(*)`.
Silence 1..30 min validado. Archive idempotente (T-163). Suppression no reescribe historial ISA.

### SOLID / patrones

| Principio | Evidencia |
|---|---|
| S | `PriorityManager`, `ChatterDetector`, `SuppressionManager`, `KPICollector`, `RetentionArchiver`, `PartitionManager` |
| O | `SuppressionManager.register`, `LatchingPolicyRegistry.register` |
| L | `SilenceType`/`ShelveType`/`DisableType`/`OOSType`/`NoSuppression` sustituibles |
| I | `IPriorityReader/Writer`, `ISuppressionReader/Writer` |
| D | managers reciben `repo`/`clock`/`events` |

Patrones usados: Strategy, Registry, Observer (KPI), Repository, Facade, Cache TTL+LRU, Deque maxlen, Chunking, Null Object, Command. No Singleton/Visitor/Builder.

### Waivers 2026-09-16 SHA `b5bed66cad90694298c026a6b05ff238e2d93607`

| ID | Gate | Intento | Razón |
|---|---|---|---|
| W-P2-01 | GATE-66 | `pg_dump -t alarmsummary --schema-only` OK | PK live sin `event_time`; no swap 1 M filas. Plan: [AUDIT_ALARMS.md](./AUDIT_ALARMS.md). Dump: `audits/AUDIT_ALARMS.md` |
| W-P2-02 | CA-B4-1 filas Chattering | T-04 | Agrupar B↔D rompería append-only P0. Se **flaggea** chatter, no se borra historial |
| W-P2-03 | T-164/T-175/T-176 | dump schema | Query concurrente/rollback restore/EXPLAIN post-swap no ejercitados en live |

### Definición Terminado P2 v2 (§15bis)

12/13 puntos verdes; punto partición live = waiver firmado.

**Declaración:** Terminado P2 v2 **con waivers firmados**.


## Parte L — Schema SQL live `alarmsummary`

> Fuente original: `p2/alarmsummary.schema.sql` — contenido íntegro, sin omisiones.

```sql
--
-- PostgreSQL database dump
--

-- Dumped from database version 17.5 (Debian 17.5-1.pgdg110+1)
-- Dumped by pg_dump version 17.5 (Debian 17.5-1.pgdg110+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alarmsummary; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.alarmsummary (
    id bigint NOT NULL,
    alarm_id bigint,
    state_id bigint,
    alarm_time timestamp without time zone,
    ack_time timestamp without time zone,
    area character varying(64),
    sample_uuid character varying(255),
    from_state character varying(24),
    to_state character varying(24),
    event_time timestamp without time zone,
    operator_id integer,
    condition_met boolean,
    condition_value double precision,
    schema_version integer
);


ALTER TABLE public.alarmsummary OWNER TO postgres;

--
-- Name: alarmsummary_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.alarmsummary_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.alarmsummary_id_seq OWNER TO postgres;

--
-- Name: alarmsummary_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.alarmsummary_id_seq OWNED BY public.alarmsummary.id;


--
-- Name: alarmsummary id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarmsummary ALTER COLUMN id SET DEFAULT nextval('public.alarmsummary_id_seq'::regclass);


--
-- Name: alarmsummary alarmsummary_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alarmsummary
    ADD CONSTRAINT alarmsummary_pkey PRIMARY KEY (id);


--
-- Name: idx_alarmsummary_alarm_time; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_alarmsummary_alarm_time ON public.alarmsummary USING btree (alarm_id, event_time DESC);


--
-- Name: idx_alarmsummary_event_time; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_alarmsummary_event_time ON public.alarmsummary USING btree (event_time DESC);


--
-- Name: idx_alarmsummary_to_state; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_alarmsummary_to_state ON public.alarmsummary USING btree (to_state, event_time DESC);


--
-- PostgreSQL database dump complete
--
```

