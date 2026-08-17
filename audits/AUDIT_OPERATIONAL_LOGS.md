# Auditoría del módulo Operational Logs — bitácora de operación

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/pages/OperationalLogs.tsx`) |
| **Alcance** | Qué está implementado hoy como bitácora de operadores tras la Operación «Bitácora Eterna»: modelo `Logs`, API `/logs`, HMI `/operational-logs`, comentarios, SAF, turno/área/relevo, métrica |
| **Fuera de alcance** | Tabla `Events` (acciones automáticas), ciclo ISA de alarmas (`AlarmSummary`), datalogger, `logs/app.log` |
| **Fecha** | 2026-08-16 (Operación «Bitácora Eterna» — evidencia de código) |
| **Clasificación** | Auditoría de bitácora operacional · confidencialidad interna |
| **Metodología** | Revisión estática post-cambio de modelo, logger, HTTP, persistencia, HMI y tests. Ejecutado: `./venv/bin/python3 -m unittest automation.tests.test_operational_logs automation.tests.test_audit_metrics -v` → **11 OK** |
| **Complementa** | `AUDIT_USER_EVENTS.md`, `AUDIT_LOGGING.md` (L2), `AUDIT_TIMEZONE.md`, `STORE_AND_FORWARD.md`, `docs/Users_Guide/OperationalLogs/index.md` |
| **Veredicto** | **A+** respecto a los CA-OL. La voz del operador journaliza con historiador caído, se lee sin ruido de comentarios/watchdog, y el autor sobrevive a un DELETE del usuario. Residual de producto (fuera de CA): firma electrónica, PDF 21 CFR, SQLite legado no reescribe FKs. |

---

## 1. Respuesta directa

**Antes (veredicto B):** `PyAutomation.create_log` devolvía `"Logs DB is not up"` si `is_db_connected()` era falso, aunque el logger ya tenía `journal_then_remote`. La página mezclaba notas, comentarios y `[HMI] heap`. No había turno/área/relevo, ni búsqueda en UI, ni Limpiar, ni `on.log` en el cliente. FKs `CASCADE`. Guía de usuario inflada.

**Ahora:** la nota del operador es `classification = "Operational"`. La vista **Bitácora** filtra `General`+`Operational` y excluye `memory-watchdog`. Un outage de PG **no impide escribir**: el façade llama al engine siempre; si `check_connectivity()` falla, queda `JournaledEnvelope` + `journaled: true` y Socket.IO `on.log`.

---

## 2. Modelo (evidencia)

Tabla Peewee `Logs` — `automation/dbmodels/logs.py`:

```35:45:automation/dbmodels/logs.py
    timestamp = TimestampField(utc=True)
    message = CharField(max_length=256)
    description = CharField(max_length=256, null=True)
    classification = CharField(max_length=128, null=True)
    user = ForeignKeyField(Users, backref='logs', null=True, on_delete='SET NULL')
    user_name = CharField(max_length=64, null=True)
    alarm = ForeignKeyField(AlarmSummary, null=True, backref='logs', on_delete='SET NULL')
    event = ForeignKeyField(Events, null=True, backref='logs', on_delete='SET NULL')
    shift = CharField(max_length=32, null=True)
    area = CharField(max_length=64, null=True)
    handover = BooleanField(default=False)
```

| Columna | Evidencia de comportamiento |
|---|---|
| `user` nullable + SET NULL | CA-OL-6: borrar usuario no borra la nota |
| `user_name` | `Logs.create` exige autor aunque `Users.read_by_username` no encuentre fila (replay SAF) |
| `shift` | whitelist `morning`/`afternoon`/`night` en `normalize_shift` |
| `area` | clip 64 |
| `handover` | bool de relevo |

Clip en escritura (no se espera a varchar de PG):

```96:107:automation/dbmodels/logs.py
        query = cls(
            message=clip_message(message),
            user=_user,
            user_name=author,
            description=clip_description(description),
            classification=clip_message(classification) if classification else None,
            timestamp=timestamp,
            event=Events.get_or_none(id=event_id) if event_id not in (None, "") else None,
            alarm=AlarmSummary.get_or_none(id=alarm_summary_id) if alarm_summary_id not in (None, "") else None,
            shift=normalize_shift(shift),
            area=clip_area(area),
            handover=bool(handover),
        )
```

Historiador ya desplegado: `Logs.ensure_schema()` añade columnas, backfill de `user_name` desde `users.username`, índice de `timestamp`, y en PostgreSQL reescribe FKs a `ON DELETE SET NULL`. Enganche al boot:

```110:118:automation/logger/core.py
        try:
            from ..dbmodels.logs import Logs

            Logs.ensure_schema()
        except Exception:
            logging.getLogger("pyautomation").warning(
                "Logs bitácora schema ensure skipped",
                exc_info=True,
            )
```

Serialize: si `user` es NULL tras un DELETE, el HMI sigue viendo `user.username` desde `user_name`.

---

## 3. Clasificación servidor (SRP de escritura)

El cliente **no** elige la familia. `POST /logs/add` elimina `timestamp`, `classification` y `user` del JSON y llama `classify_write`:

```55:71:automation/modules/events/resources/logs.py
        user = Api.get_current_user()
        payload = dict(api.payload or {})
        payload.pop("timestamp", None)
        payload.pop("classification", None)
        payload.pop("user", None)
        from ....utils.operational_log_audit import classify_write, clip_message

        payload["user"] = user
        payload["message"] = clip_message(payload.get("message"))
        payload["classification"] = classify_write(
            event_id=payload.get("event_id"),
            alarm_summary_id=payload.get("alarm_summary_id"),
            description=payload.get("description"),
        )
        payload["handover"] = bool(payload.get("handover"))

        log, message = app.create_log(**payload)
```

Reglas (`automation/utils/operational_log_audit.py`):

| Condición | `classification` | Emisor real |
|---|---|---|
| `event_id` presente | `Event` | comentario en `/events` |
| `alarm_summary_id` presente | `Alarm` | comentario en `/alarms/summary` |
| `description == memory-watchdog` | `System` | `useMemoryWatchdog` |
| resto | `Operational` | modal de bitácora |

Watchdog (sigue yendo a `Logs`, pero ya no a la vista Bitácora):

```27:30:hmi/src/hooks/useMemoryWatchdog.ts
          void createLog({
            message,
            description: "memory-watchdog",
          }).catch(() => undefined);
```

`POST /logs/add` **no** lleva `@require_remote_db` (sí lo llevan `filter_by` y `lasts`). Eso es deliberado: anotar en outage.

---

## 4. Persistencia SAF (CA-OL-1)

El hueco era el façade, no el journal. Hoy `create_log` **no** pregunta `is_db_connected()`:

```4332:4371:automation/core.py
    def create_log(
        self, 
        message:str, 
        user:User, 
        ...
        )->tuple:
        r"""
        Creates a logbook entry. Journals even when the historian is down.
        """
        log, message = self.logs_engine.create(...)
        if log and self.sio:
            ...
                self.sio.emit("on.log", data=payload)
        return log, message
```

`LogsLogger.create` journaliza siempre; el write remoto solo si hay conectividad:

```76:86:automation/logger/logs.py
        connected = bool(user) and self.check_connectivity()
        result, _ = journal_then_remote(record, _write, connected)
        try:
            from ..utils.audit_metrics import note_log_persisted
            note_log_persisted()
        except Exception:
            pass
        if result is not None and not (isinstance(result, tuple) and result[0] is None):
            return result
        return JournaledEnvelope(record.payload()), "journaled"
```

`PersistableRecord.log` es `critical=True`, dominio `DOMAIN.LOG`, con `shift`/`area`/`handover`/`user_name` en el body.

Replay: `_write_logs` **ya no hace `continue` si el User no existe**; crea con `user_name`:

```256:277:automation/persistence/remote.py
    def _write_logs(self, payloads: Sequence[Mapping]) -> int:
        ...
            user = _user_for_username(username)
            created, _ = Logs.create(
                ...
                user=user,
                user_name=item.get("user_name") or username,
                ...
            )
```

Test de evidencia:

- `test_create_log_does_not_require_db_live` — `is_db_connected=False` → igual llama `logs_engine.create` y emite `on.log`
- `test_logger_journals_when_connectivity_fails` — `journal_then_remote(..., connected=False)` → `"journaled"`

---

## 5. Lectura / filtros (CA-OL-2, CA-OL-3)

Backend `Logs.filter_by`:

- `classifications: list` → `LOWER(classification) IN (...)`
- `search` → `message CONTAINS term OR description CONTAINS term` (no AND)
- `exclude_description` → NULL o distinto (watchdog)
- filtro por usuario: FK **o** `user_name` (notas de cuentas borradas)

```160:177:automation/dbmodels/logs.py
        if search:
            term = search.lower()
            query = query.where(
                fn.LOWER(cls.message).contains(term)
                | fn.LOWER(cls.description).contains(term)
            )
        ...
        if exclude_description:
            excluded = exclude_description.lower()
            query = query.where(
                cls.description.is_null(True)
                | (fn.LOWER(cls.description) != excluded)
            )
```

HMI, vista por defecto **notebook**:

```41:55:hmi/src/pages/OperationalLogs.tsx
const WATCHDOG_DESCRIPTION = "memory-watchdog";
const NOTEBOOK_CLASSIFICATIONS = ["General", "Operational"];

function viewFilters(view: LogView): Pick<LogFilter, "classifications" | "exclude_description"> {
  if (view === "notebook") {
    return {
      classifications: NOTEBOOK_CLASSIFICATIONS,
      exclude_description: WATCHDOG_DESCRIPTION,
    };
  }
  if (view === "comments") {
    return { classifications: ["Event", "Alarm"] };
  }
  if (view === "system") {
    return { classifications: ["System"] };
```

`General` entra en Bitácora para no perder notas anteriores a esta operación. El watchdog nuevo es `System`; el legado `General`+`memory-watchdog` lo saca `exclude_description`.

Rango default **Last Day** (24 h), no Last Hour. Limpiar restaura notebook + 24 h:

```368:394:hmi/src/pages/OperationalLogs.tsx
  const handleClearFilters = () => {
    ...
    setLogView("notebook");
    ...
    setPresetDate("Last Day");
    ...
    setFilters({
      page: 1,
      limit: 20,
    });
```

El botón **Limpiar** está en el JSX (`onClick={handleClearFilters}`).

Live refresh:

```193:197:hmi/src/pages/OperationalLogs.tsx
  useEffect(() => {
    return socketService.onLogUpdate(() => {
      loadLogsRef.current();
    });
  }, []);
```

```152:154:hmi/src/services/socket.ts
  onLogUpdate(callback: (log: Record<string, unknown>) => void): () => void {
    return this.subscribe<Record<string, unknown>>("on.log", callback);
  }
```

Outage de lectura: 503 **no** vacía filas ya mostradas (notas `journaled` siguen en pantalla):

```281:284:hmi/src/pages/OperationalLogs.tsx
      if (isDbUnavailableError(e)) {
        setError(null);
        return;
      }
```

Modal de alta: `message` `maxLength={256}`, `shift`, `area`, `handover`. Payload `createLog({ message, shift, area, handover })` — sin `event_id` → `Operational`.

---

## 6. Métrica (CA-OL-7)

Cola aparte de Events (no se mezclan tasas):

```29:59:automation/utils/audit_metrics.py
def note_log_persisted() -> None:
    ...
def snapshot() -> dict:
    ...
        "LOGS_RATE_PER_MIN": round(logs_rate, 2),
        "LOGS_RATE_ALERT": bool(logs_rate > LOGS_ALERT_PER_MIN),
        "LOGS_RATE_ALERT_THRESHOLD": LOGS_ALERT_PER_MIN,
```

`GET /api/health/system` hace `**_event_rate_metrics()` y `snapshot()` ya incluye las claves `LOGS_*`. Umbral `LOGS_ALERT_PER_MIN = 30`. Test: `test_log_rate_is_independent_of_events`.

---

## 7. Criterios de aceptación vs código

| ID | Criterio | Evidencia | Estado |
|---|---|---|---|
| **CA-OL-1** | Anotar con BD caída y replicar | `create_log` sin gate; `journal_then_remote(..., connected=False)`; `_write_logs`; tests SAF | **Cumple** |
| **CA-OL-2** | Vista default sin Event/Alarm/watchdog | `viewFilters("notebook")` + `exclude_description` | **Cumple** |
| **CA-OL-3** | Búsqueda message OR description | `Logs.filter_by` `search`; input HMI `payload.search` | **Cumple** |
| **CA-OL-4** | Turno y área en alta | modelo + `logs_model` + modal | **Cumple** |
| **CA-OL-5** | Limpiar filtros | `handleClearFilters` cableado al JSX | **Cumple** |
| **CA-OL-6** | SET NULL + nombre conservado | FKs modelo; `ensure_schema` PG; serialize `user_name` | **Cumple** (SQLite *nuevo*; legado SQLite no ALTER FK) |
| **CA-OL-7** | `LOGS_RATE_PER_MIN` | `audit_metrics.snapshot` + health | **Cumple** |
| **CA-OL-8** | Guía = implementación | `docs/Users_Guide/OperationalLogs/index.md` reescrita | **Cumple** |

---

## 8. Tests ejecutados

```
./venv/bin/python3 -m unittest automation.tests.test_operational_logs automation.tests.test_audit_metrics -v
Ran 11 tests in 0.011s
OK
```

| Test | Qué cubre |
|---|---|
| `test_operator_note_is_operational` | classify default |
| `test_event_comment_beats_free_text` | event_id gana |
| `test_alarm_comment` | alarm_summary_id |
| `test_watchdog_is_system_not_notebook` | memory-watchdog → System |
| `test_shift_whitelist` | morning vs basura |
| `test_message_is_clipped` | 300 → ≤256 + `…` |
| `test_create_log_does_not_require_db_live` | façade sin BD |
| `test_logger_journals_when_connectivity_fails` | connected=False |
| `test_log_rate_is_independent_of_events` | métrica L2 vs L3 |

No hay test de integración HTTP ni de `ensure_schema` contra PostgreSQL real (residual de prueba, no de producto).

---

## 9. Inventario de archivos tocados

| Pieza | Archivo |
|---|---|
| Contrato de clasificación / clip / turno | `automation/utils/operational_log_audit.py` |
| Tabla, filtro, SET NULL, ensure | `automation/dbmodels/logs.py` |
| Logger SAF + métrica | `automation/logger/logs.py` |
| Schema al boot | `automation/logger/core.py` |
| Façade sin gate BD | `automation/core.py` `create_log` |
| HTTP add/filter | `automation/modules/events/resources/logs.py` |
| Journal payload | `automation/persistence/records.py` `PersistableRecord.log` |
| Replay | `automation/persistence/remote.py` `_write_logs` |
| Health | `automation/utils/audit_metrics.py`, `modules/health/resources/health.py` |
| Comments 404 | `dbmodels/events.py` `get_comments`, `dbmodels/alarms.py` `get_alarm_summary_comments` |
| HMI | `hmi/src/pages/OperationalLogs.tsx`, `services/logs.ts`, `services/socket.ts` |
| i18n | `hmi/src/locales/{es,en}.json` |
| Guía | `docs/Users_Guide/OperationalLogs/index.md` |
| Tests | `automation/tests/test_operational_logs.py`, `test_audit_metrics.py` |

---

## 10. Residual (honesto)

| ID | Severidad | Qué dice el código |
|---|---|---|
| **OL-R1** | Info | No hay firma, PDF ni e-logbook 21 CFR. No estaba en CA. |
| **OL-R2** | Info | `ensure_schema` reescribe FKs solo si el dialecto contiene `"postgres"`. SQLite de tests/nuevos usa el modelo Peewee; un `.db` SQLite antiguo puede seguir en CASCADE. |
| **OL-R3** | Info | CSV cliente `limit: 10000`, sin BOM. |
| **OL-R4** | Info | Un solo almacén físico `Logs`. La separación Bitácora/Comentarios/Sistema es de **vista y clasificación**, no de tabla. |
| **OL-R5** | Info | `filter_by` / `lasts` siguen exigiendo historiador (`@require_remote_db`). En outage se escribe, no se pagina contra PG. |
| **OL-R6** | Info | `LogsLogger.get_summary` sigue llamando `Logs.serialize()` como classmethod (muerto, sin ruta HTTP). |

---

## 11. Cómo verificar en planta

1. `/operational-logs` vista Bitácora: no hay `Event`/`Alarm` ni `[HMI] heap`.
2. Agregar nota con turno noche + área + relevo → fila `Operational`.
3. Buscar una palabra del mensaje (Enter o Filtrar).
4. Limpiar → Bitácora + últimas 24 h.
5. Vista Comentarios: aparece un comentario hecho desde Eventos.
6. Cortar historiador → Agregar → 200 con `journaled: true`; reconectar → fila en PG.
7. `GET /api/health/system` → `LOGS_RATE_PER_MIN`, `LOGS_RATE_ALERT`, `LOGS_RATE_ALERT_THRESHOLD`.

---

## 12. Conclusión

La evidencia de código cubre los ocho CA de Bitácora Eterna. El gap que bajaba el módulo a **B** (escritura bloqueada sin BD + cuaderno mezclado) está cerrado en `create_log`, `LogsLogger.create`, `classify_write` y `viewFilters("notebook")`.

**Veredicto: A+** como bitácora de planta. No es un e-logbook regulado; no lo pretendían los CA.
