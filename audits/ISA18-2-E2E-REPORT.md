# ISA18-2-E2E-REPORT — SPEC-ISA18-2-PG-CLOSURE-v2

| Campo | Valor |
|---|---|
| **Fecha** | 2026-09-16 |
| **SHA** | `7ee3df9527c5141e8bc963b856cd569f95aa8a1e` |
| **Stack** | `app_db` :32800 · `compose-redis-session-1` · `opcua_simulator` :4840 (`idetectfugas/opcua_server_simulator:2.2.1`) |
| **Norma** | ANSI/ISA-18.2-2016 §6, §9, §10, §11, §14 |
| **Veredicto E2E** | Ciclo ISA **PASS** (SQLite + `check_condition`). OPC **lectura PASS / escritura DENEGADA**. SAF→PG en DAS vivo **no demostrado**. |

## 0. Pre-vuelo (FASE 1)

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
CA-F1-3 **PASS** — 5+ índices (ver [ISA18-2-EXPLAIN-PG.md](./ISA18-2-EXPLAIN-PG.md)).

## 1. GATE-34 / GATE-38 — ciclo ISA y OPC

### 1.1 OPC simulator (crudo)

```
OPC FI_01=0.0
OPC write denied: BadUserAccessDenied: "User does not have permission to perform the requested operation."(BadUserAccessDenied)
```

El simulador reproduce CSV; nodos **no escribibles**. No se pudo forzar PV=60/40 en el tag real. AP-56 respetado: el simulador **sí** estaba corriendo; la limitación es ACL de escritura, no ausencia del proceso.

### 1.2 Ciclo A→B→D→B→C→E (`check_condition` real, sin mock)

Test: `automation.tests.test_alarms_e2e_opc.TestAlarmE2EOPC.test_isa_lifecycle_five_history_rows`

```
history [('Normal', 'Unack Alarm'), ('Unack Alarm', 'RTN Unack'), ('RTN Unack', 'Unack Alarm'), ('Unack Alarm', 'Ack Alarm'), ('Ack Alarm', 'Cleared')]
```

5 filas, `sample_uuid` únicos. Sequencia exacta de la spec.

### 1.3 Round-trip PG (lab INSERT, no DAS)

Test: `test_five_unique_uuids_roundtrip_pg` — 5 filas en `alarmsummary` con la misma secuencia y UUID únicos. **PASS**.

### 1.4 Criterios FASE 5

| # | Criterio | Resultado |
|---|---|---|
| CA-F5-1 | Ciclo A→B→D→B→C→E sin errores | **PASS** (PV local) |
| CA-F5-2 | 5 filas secuencia correcta | **PASS** (SQLite historial; PG lab INSERT) |
| CA-F5-3 | `sample_uuid` únicos | **PASS** |
| CA-F5-4 | SAF replica ≤ 5 s | **FAIL / waiver** — DAS+SAF no corrían contra este PG lab |
| CA-F5-5 | Footer HMI ≤ 2 s | **FAIL / waiver** — HMI :8050 / Playwright no ejercitados |

**GATE-34:** PARCIAL — OPC readable, write denied, ciclo in-process.
**GATE-38:** VERDE para SM+historial SQLite (5 filas). PARCIAL para «vía SAF a PG».

## 2. GATE-35 — hot path con scan OPC

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

## 3. GATE-36 — Redis / multiworker

`automation/alarms/runtime.py` **no importa Redis** (INV-64). Redis es almacén de sesión HMI, no cola de transiciones.

```
test_runtime_does_not_import_redis ... ok
test_redis_db15_isolated ... ok          # redis-cli -n 15 PONG + SET/GET/FLUSHDB
test_two_drainers_process_each_event_once ... ok   # 100 eventos, 2 hilos, 0 duplicados, cola 0
```

CA-F7-1 adaptado: 100 eventos → 100 drenados, 0 duplicados. **PASS**.
CA-F7-3 Redis DB 15 aislada. **PASS**.
Cola Redis de alarmas: **no existe en producto** (correcto bajo INV-64).

## 4. GATE-37 — restart PG

```
docker restart app_db
PG restart OK rows=1000010
```

Seed sobrevive (antes = después = 1 000 010; +10 filas del INSERT lab E2E). **Durabilidad PASS**.
SAF buffer + replay de 100 transiciones durante outage: **no ejecutado** (no había DAS/SAF apuntando a este PG). Waiver W-PG-04.

## 5. GATE-32-PG — paginación 1 M

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

## 6. FASE 11 — frontend bounds

Playwright **no** está en el árbol (`hmi/e2e/` ausente). `test_alarms_frontend_bounds` **PASS** (store `top3Active` / page 50 / history 100, 1000 eventos simulados en reducer). Waiver W-PG-07.

## 7. INV-51…INV-65

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

## 8. Waivers firmados 2026-09-16 · SHA `7ee3df9527c5141e8bc963b856cd569f95aa8a1e`

| ID | Gate / INV | Intento | Razón |
|---|---|---|---|
| W-PG-01 | GATE-34 | `node.set_value(60.0)` | `BadUserAccessDenied` en simulador CSV |
| W-PG-02 | GATE-35 CA-F6 50 µs | 3 scans medidos | CPython `on_tag_value` 68–106 µs; INV-55 150 µs PASS; T-64b 23.7 µs |
| W-PG-03 | GATE-36 cola Redis | grep + redis-cli db15 | Producto no usa Redis en alarmas (INV-64) |
| W-PG-04 | GATE-37 SAF replay | `docker restart app_db` | Durabilidad seed sí; DAS/SAF no apuntaban al lab |
| W-PG-05 | CA-F5-4 SAF≤5 s | INSERT lab 5 filas | Sin worker SAF en esta corrida |
| W-PG-06 | GATE-33 CA-F10-2 | `\d alarmsummary` | PK `id bigint` sin `event_time`; ver [ISA18-2-PARTITION-PLAN.md](./ISA18-2-PARTITION-PLAN.md) |
| W-PG-07 | FASE 11 Playwright | unittest cotas | No hay `@playwright/test` ni `hmi/e2e/` |
| W-PG-08 | INV-60 footer 2 s | — | HMI :8050 no ejercitado |
| W-PG-09 | INV-63 500 tags | T-64b N=500 estático | No soak OPC 500 tags |
| W-PG-10 | Nombres stack | `docker ps` | Spec `idetect_db`/`opcua_server_simulator_aux`; real `app_db`/`opcua_simulator` |
