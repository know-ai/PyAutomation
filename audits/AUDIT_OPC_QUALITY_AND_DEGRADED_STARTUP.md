# Auditoría: calidad OPC UA y arranque degradado — verificación post-spec 09 + 10

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`automation/` + HMI `hmi/src/`) |
| **Alcance** | Verificación de [specs/09-OPC-QUALITY-AND-DEGRADED-STARTUP.md](../specs/09-OPC-QUALITY-AND-DEGRADED-STARTUP.md) v1.0 (P0/P1) **y** [specs/10-OPC-QUALITY-A-PLUS.md](../specs/10-OPC-QUALITY-A-PLUS.md) v2.0 (A+) |
| **Fecha** | 2026-08-21 |
| **Evidencia** | Revisión estática del código + `automation/tests/test_opc_quality.py` — **19 OK / 3 skipped** (soak planta) |
| **Baseline** | Auditoría gap 2026-08-20 (mismo archivo, § histórico): **B− operativo / D calidad de señal** |
| **Complementa** | [AUDIT_SIGNAL_CONDITIONING.md](./AUDIT_SIGNAL_CONDITIONING.md), [AUDIT_DB.md](./AUDIT_DB.md), [AUDIT_STORE_AND_FORWARD.md](./AUDIT_STORE_AND_FORWARD.md), [docs/opc-quality-runbook.md](../docs/opc-quality-runbook.md) |
| **Normas de referencia** | OPC UA Part 4 (StatusCodes), ISA-18.2, IEC 61508 (SIL-ready, sin certificación), prácticas DCS (hold-last, inhibit, stale PV, degraded mode) |
| **Veredicto vigente** | **A− disponibilidad** · **A− calidad de señal** (A+ condicionado a soak 24 h) · **A Login / UX degradada** |
| **Clasificación** | Auditoría de verificación · calidad de señal · degradación segura |

---

## 0. Respuesta directa

| Escenario | ¿Qué hace PyAutomation **ahora** (2026-08-21)? | Spec | Grado nuclear / DCS |
|---|---|---|---|
| **Servidor OPC publica BAD / UNCERTAIN / NaN** | StatusCode → `Quality` (severity + substatus); hold-last en PV; gate de proceso; `ALM.QUALITY.*`; badge G/U/B + tooltip substatus | 09+10 | **A−** (A+ pendiente soak/SIL) |
| **Arranque / pérdida con OPC offline** | App no bloquea; `ALM.OPCUA.*`; reconnect; tags del cliente → **BAD/stale** sin pisar last-good; `ALM.QUALITY.*` | 09+10 | **A−** |
| **Arranque sin historiador** | App no bloquea; SAF; Login/Signup **503 + `event_id` visible** en HMI; banner «modo degradado» | 09+10 | **A** |
| **Operador cambia política UNCERTAIN** | Settings → checkbox; PUT `/settings/update`; caché hot path sin `json.load` | 10 | **A−** |

Cadena hot path **post-spec 10**:

```
OPC UA datachange (subscription.py)
  → SourceTimestamp + StatusCode
  → map_opc_status() → Quality(severity, opc_code, substatus)
  → cvt.set_value_fast(..., quality, opc_code, substatus)
  → Tag.set_value: Bad/NaN/Inf → hold-last + stale; GOOD → actualiza PV
  → QualityAlarmEngine → SYS.QUALITY.<tag> / ALM.QUALITY.<tag> (+ Event rate-limited)
  → Alarm.notify: gate BAD; UNCERTAIN vía get_inhibit_uncertain_quality() (caché)
  → serialize_socket { quality, quality_label, quality_substatus, stale, stale_age_ms }
  → HMI QualityBadge G/U/B* (+ substatus tooltip)
```

---

## 1. Matriz de criterios de aceptación (CA-OQ)

| ID | Criterio | Resultado | Evidencia primaria | Test |
|---|---|---|---|---|
| **CA-OQ-01** | `CVTEngine.set_value(..., quality=BAD)` persiste quality | **PASS** | `cvt.py` `set_value` → `set_value_fast` | `TestCVTQualityPropagation` |
| **CA-OQ-02** | StatusCode Bad → CVT quality ≠ GOOD | **PASS** | `subscription.py` `_extract_status_quality` + `datachange_notification` | `TestSubscriptionStatusCode` |
| **CA-OQ-03** | Bad/NaN/Inf no modifica PV raw; sí quality/stale | **PASS** | `tag.py` `set_value` hold-last | `TestHoldLast` |
| **CA-OQ-04** | `Alarm.notify` no evalúa setpoint en BAD | **PASS** | `alarms/__init__.py` `_quality_allows_process_evaluation` | `TestAlarmQualityGate` |
| **CA-OQ-05** | Disconnect OPC → tags BAD/stale sin pisar last-good | **PASS** | `models.py` + `cvt.mark_opcua_client_tags_stale` | `TestOpcDisconnectStale` |
| **CA-OQ-06** | HMI badge G/U/B + stale age (+ substatus) | **PASS** | `QualityBadge.tsx`, Tags, Alarms, StripChart | Revisión estática + suite |
| **CA-OQ-07** | Login 503 incluye `event_id` (API) | **PASS** | `users.py` + `db_audit.ensure_degraded_event_id` | `TestLoginEventId` |
| **CA-OQ-08** | Banner modo degradado si BD offline | **PASS** | `DegradedModeBanner.tsx` + `MainLayout.tsx` | Revisión estática HMI |
| **CA-OQ-09** | `ALM.QUALITY.<tag>` ON en BAD/stale, OFF en GOOD | **PASS** | `quality_gate.py` + `quality_alarms.py` + hook `Tag` | `TestQualityAlarmEngine` |
| **CA-OQ-10** | Login/Signup HMI muestra `event_id` | **PASS** | `Login.tsx` / `Signup.tsx` + `DatabaseConfigForm` | `TestHmiQualitySurfaces` |
| **CA-OQ-11** | Toggle UNCERTAIN en caliente (caché) | **PASS** | `set_inhibit_uncertain_quality` + `QualityPolicyPanel.tsx` | `TestInhibitUncertainCache` |
| **CA-OQ-12** | Trends históricos / DataLogger badge o «sin calidad» | **PASS** | `HistoricalQualityLegend.tsx` | `TestHmiQualitySurfaces` |
| **CA-OQ-13…15** | Soak 24 h planta | **PENDIENTE** | [opc-quality-runbook.md](../docs/opc-quality-runbook.md) § 4 | `TestSoakDocumented` (3 skip) |

**Suite:** `./venv/bin/python -m unittest automation.tests.test_opc_quality` — **22 tests: 19 OK, 3 skipped** (2026-08-21).

---

## 2. Inventario de código (evidencia)

### 2.1 Mapeo StatusCode → Quality (borde OPC)

| Artefacto | Rol | Estado |
|---|---|---|
| `automation/signal_conditioning/quality.py` | `Quality` frozen; `map_opc_status`; `status_code_to_quality` (bits 30–31); `status_code_substatus`; caché inhibit | ✅ |
| `automation/opcua/subscription.py` | `_extract_status_quality` → `Quality`; `_quality_write_kwargs` propaga `opc_code`/`substatus` | ✅ |

```42:50:automation/signal_conditioning/quality.py
@dataclass(frozen=True)
class Quality:
    """Immutable quality snapshot at the OPC / CVT boundary."""

    severity: float = GOOD
    opc_code: int | None = None
    substatus: str | None = None
    stale: bool = False
    stale_age_ms: int | None = None
```

```153:159:automation/signal_conditioning/quality.py
def map_opc_status(status_code) -> Quality:
    """OPC-edge mapper: StatusCode → immutable Quality (severity + forensics)."""
    return Quality(
        severity=status_code_to_quality(status_code),
        opc_code=_status_int(status_code),
        substatus=status_code_substatus(status_code),
    )
```

```43:49:automation/opcua/subscription.py
def _extract_status_quality(data):
    """Pull StatusCode from a datachange notification payload → Quality."""
    try:
        status = data.monitored_item.Value.StatusCode
    except Exception:
        return map_opc_status(None)
    return map_opc_status(status)
```

```380:386:automation/opcua/subscription.py
    def datachange_notification(self, node, val, data):
        ...
        timestamp = data.monitored_item.Value.SourceTimestamp
        quality = _extract_status_quality(data)
        self.update_tag_value(node, val, timestamp, quality=quality)
```

El hot path del Tag sigue en **float** `1.0 / 0.5 / 0.0` (O(1), sin allocation extra en el camino GOOD).

### 2.2 Propagación CVT (bug P0 cerrado + forense)

| Artefacto | Antes (2026-08-20) | Ahora |
|---|---|---|
| `CVTEngine.set_value` | Descartaba 4.º arg → siempre GOOD | Reenvía `quality`, `opc_code`, `substatus` |

```1247:1253:automation/tags/cvt.py
    def set_value(self, id:str, value, timestamp:datetime, quality:float=1.0, opc_code:int|None=None, substatus:str|None=None):
        r"""
        Tag value write. Acquisition uses the fast path; CRUD stays on __query.
        """
        return self.set_value_fast(
            id, value, timestamp, quality=quality, opc_code=opc_code, substatus=substatus
        )
```

Impacto colateral: publicación wavelet `.f` vía `app.cvt.set_value(..., quality=UNCERTAIN)` ya no pierde calidad ([AUDIT_SIGNAL_CONDITIONING.md](./AUDIT_SIGNAL_CONDITIONING.md)).

### 2.3 Hold-last + stale + hook de calidad en Tag

| Comportamiento | Evidencia |
|---|---|
| Bad / NaN / Inf → no `value.set_value`; sí `quality`, `stale`, `stale_timestamp` | `tag.py` `set_value` |
| Persiste `opc_status_code` / `quality_substatus` | kwargs opcionales |
| Transición degraded → `notify_quality_transition` **fuera del lock** | `_notify_quality_engine` |
| Wire | `serialize` / `serialize_socket`: `quality`, `quality_label`, `quality_substatus`, `opc_status_code`, `stale`, `stale_age_ms` |

```351:358:automation/tags/tag.py
    def _notify_quality_engine(self, previous_degraded: bool, degraded: bool) -> None:
        if bool(previous_degraded) == bool(degraded):
            return
        try:
            from ..alarms.quality_gate import notify_quality_transition

            notify_quality_transition(self, degraded=bool(degraded))
```

### 2.4 Gate ISA-18.2 en alarmas de proceso (caché, sin I/O)

```350:363:automation/alarms/__init__.py
    def _quality_allows_process_evaluation(self) -> bool:
        """Gate process setpoints on PV quality (ISA-18.2 inhibit on Bad)."""
        from ..signal_conditioning.quality import is_process_alarm_allowed
        ...
            from ..signal_conditioning.quality import get_inhibit_uncertain_quality

            inhibit_uncertain = bool(get_inhibit_uncertain_quality())
        ...
        return is_process_alarm_allowed(quality, inhibit_uncertain=inhibit_uncertain)
```

| Política | Default | Configurable |
|---|---|---|
| BAD | **Inhibe** setpoint | — |
| UNCERTAIN | **Permite** evaluación | `alarm_inhibit_uncertain_quality=true` (Settings UI + API) |
| GOOD | Evalúa | — |

El shelve timeout permanece **fuera** del gate (lifecycle ISA-18.2 intacto).

### 2.5 `ALM.QUALITY.<tag>` (spec 10 / CA-OQ-09)

| Pieza | Ruta | Comportamiento |
|---|---|---|
| Engine | `automation/alarms/quality_gate.py` | Transición BAD/stale ↔ GOOD; `threading.local` anti-reentrada; Event rate-limited 5 s |
| BOOL ISA | `automation/utils/quality_alarms.py` | Lazy `SYS.QUALITY.<tag>` / `ALM.QUALITY.<tag>`; excluye `SYS.*`, `ALM.*`, `.f` |
| Fail-safe | Ambos | Nunca levantan excepción al hot path de adquisición |

```24:38:automation/alarms/quality_gate.py
def notify_quality_transition(tag, *, degraded: bool) -> None:
    """Drive ALM.QUALITY and a forensic Event. Never raises. Never re-enters."""
    if getattr(_tls, "active", False):
        return
    if tag is None or not is_quality_subject(tag):
        return
    _tls.active = True
    try:
        name = getattr(tag, "name", "") or ""
        set_quality_degraded(name, degraded)
        _emit_quality_event(tag, degraded=degraded)
    ...
```

Coexiste con `ALM.OPCUA.*` (enlace) y con setpoints de proceso (inhibidos, no sustituidos).

### 2.6 Stale al disconnect OPC

`_sync_connection_alarm(True)` en connect-fail / disconnect / lost-link → `mark_opcua_client_tags_stale` escribe valor held con `quality=BAD` → hold-last garantiza el PV y dispara `ALM.QUALITY.*`.

### 2.7 Login 503 + `event_id` visible (CA-OQ-07 / 10)

```18:25:automation/modules/users/resources/users.py
def _database_unavailable_payload(message: str, details: str) -> dict:
    event_id = database_connection_auditor.ensure_degraded_event_id()
    return {
        "message": message,
        "error_type": "database_connection_error",
        "details": details,
        "event_id": event_id,
    }
```

| Capa | Artefacto | Estado |
|---|---|---|
| API | `users.py` + `db_audit.ensure_degraded_event_id` | ✅ UUID hex estable por episodio |
| HMI Login | `Login.tsx` `extractBackendEventId` | ✅ |
| HMI Signup | `Signup.tsx` | ✅ |
| Formulario | `DatabaseConfigForm.tsx` prop `eventId` + alert | ✅ |
| i18n | `auth.databaseUnavailableWithEventId` ES/EN | ✅ |

### 2.8 Settings — política UNCERTAIN (CA-OQ-11)

```93:99:automation/modules/settings/resources/settings.py
        if 'alarm_inhibit_uncertain_quality' in data:
            inhibit = bool(data['alarm_inhibit_uncertain_quality'])
            app.set_app_config(alarm_inhibit_uncertain_quality=inhibit)
            try:
                from ....signal_conditioning.quality import set_inhibit_uncertain_quality

                set_inhibit_uncertain_quality(inhibit)
```

| Capa | Artefacto |
|---|---|
| API | PUT `/settings/update` campo `alarm_inhibit_uncertain_quality` |
| Caché | `set_inhibit_uncertain_quality` / `get_inhibit_uncertain_quality` |
| HMI | `QualityPolicyPanel.tsx` en Settings (capítulo `settings-quality`) |

### 2.9 HMI — superficies de calidad

| Superficie | Artefacto | Comportamiento |
|---|---|---|
| Tags | `Tags.tsx` + `QualityBadge` | Badge + tooltip substatus / stale age |
| Alarmas | `AlarmTableRow.tsx` | Badge sobre valor del tag |
| Trends RT | `StripChart.tsx` | Badge por tag + substatus |
| Trends históricos | `Trends.tsx` + `HistoricalQualityLegend` | Live G/U/B o «N/A» |
| DataLogger | `DataLogger.tsx` + misma leyenda | Idem |
| Modo degradado | `DegradedModeBanner.tsx` en `MainLayout` | Visible si BD offline |
| Settings | `QualityPolicyPanel.tsx` | Toggle UNCERTAIN en caliente |

---

## 3. Contraste baseline → post-spec 09 → post-spec 10

| Requisito DCS / spec | Baseline 2026-08-20 | Post-09 | Post-10 (ahora) |
|---|---|---|---|
| StatusCode → quality CVT | No | Sí (severidad) | **Sí + substatus / opc_code** |
| Hold-last PV raw | No (solo `.f`) | Sí | Sí |
| Inhibit alarmas proceso en Bad | No | Sí | Sí (caché, no JSON) |
| Toggle UNCERTAIN en Settings | No | Solo config archivo | **UI + API en caliente** |
| Disconnect → Bad/stale | Solo BOOL enlace | BOOL + PVs | + `ALM.QUALITY.*` |
| Badge HMI G/U/B | No | Tags/Alarms/StripChart | **+ Trends históricos / DataLogger** |
| Login `event_id` | No | Solo API | **Visible al operador** |
| Banner degradado | Overlay parcial | Persistente | Persistente |
| `ALM.QUALITY.<tag>` | No | Residual OQ-R1 | **Implementado** |
| Certificación SIL / soak 24 h | Fuera / no | Fuera / no | Procedimiento documentado; **runtime pendiente** |

---

## 4. Disponibilidad (no regresiones)

| Capacidad previa (A−) | ¿Intacta? | Notas |
|---|---|---|
| Arranque no bloqueante OPC down | **Sí** | Stale mark fail-safe |
| Reconnect `LoggerWorker` + re-subscribe | **Sí** | GOOD limpia stale y `ALM.QUALITY.*` |
| Arranque BD down + SAF | **Sí** | Sin cambios en journal/replicator |
| Alarmas BOOL `ALM.OPCUA.*` / `ALM.DB.Connection` | **Sí** | Coexisten con `ALM.QUALITY.*` |
| Hot path sin I/O de config | **Sí** | `get_inhibit_uncertain_quality()` O(1) tras primer load |

---

## 5. Tests y cobertura

| Suite | Cobertura vs CA | Resultado (2026-08-21) |
|---|---|---|
| `automation/tests/test_opc_quality.py` | CA-OQ-01…12 + helpers; 13–15 documentados/skipped | **19 OK, 3 skipped** |
| `TestQualityAlarmEngine` | CA-OQ-09 (subject filter + ON/OFF) | OK |
| `TestInhibitUncertainCache` | CA-OQ-11 | OK |
| `TestHmiQualitySurfaces` | CA-OQ-10, 12 (artefactos HMI) | OK |
| `TestSoakDocumented` | CA-OQ-13…15 runbook + skip runtime | 1 OK + 3 skip |
| Wavelet hold-last BAD | Alineado a calidad BAD (no UNCERTAIN forzado) | OK (suite wavelet) |

Pendiente de formalizar (bloquea **A+**, no **A−**):

- Soak planta 24 h según [opc-quality-runbook.md](../docs/opc-quality-runbook.md) § 4.
- E2E browser de badge/banner (hoy revisión estática + asserts de archivos HMI).
- Persistencia de quality por muestra en historiador (fuera de alcance spec 10; badge histórico usa live CVT).

---

## 6. Hallazgos residuales (priorizados)

| ID | Severidad | Hallazgo | Estado |
|---|---|---|---|
| **OQ-R1** | — | `ALM.QUALITY.<tag>` | **Cerrado** — `quality_gate.py` + `quality_alarms.py` |
| **OQ-R2** | — | Toggle UNCERTAIN en Settings | **Cerrado** — `QualityPolicyPanel` + caché |
| **OQ-R3** | — | Login HMI sin `event_id` | **Cerrado** — form + toast |
| **OQ-R4** | — | Trends históricos sin badge | **Cerrado** — `HistoricalQualityLegend` |
| **OQ-R5** | Info | Subcódigo Part 4 | **Cerrado en wire/tooltip**; no se historifica por muestra |
| **OQ-R6** | Info | Sin V&V / IAD / certificación SIL | Fuera de alcance |
| **OQ-R7** | Medio (V&V) | Soak 24 h CA-OQ-13…15 no ejecutado en planta | Procedimiento listo; bloquea veredicto **A+** |

---

## 7. Veredicto

| Dimensión | Baseline | Meta 09 | Meta 10 | **Veredicto 2026-08-21** |
|---|---|---|---|---|
| Disponibilidad (arranque / reconnect / SAF) | **A−** | Mantener | Mantener | **A−** |
| Calidad de señal (StatusCode → CVT → alarmas → HMI) | **D** | **B+ / A−** | **A− / A+** | **A−** (`ALM.QUALITY.*` + Settings + substatus; **A+** bloqueado por soak) |
| Trazabilidad Login / modo degradado UX | **B** | **A−** | **A** | **A** (`event_id` visible) |

**Conclusión:** las specs 09 y 10 están cerradas en código con evidencia unitaria y estática. El producto ya no engaña al operador con GOOD aparente: hold-last, inhibit, `ALM.QUALITY.*`, badge en RT e histórico, y correlación Login↔Events. El salto a **A+** en calidad de señal requiere completar el soak 24 h (CA-OQ-13…15).

---

## 8. Histórico

### 8.1 Gap analysis 2026-08-20 (obsoleto)

StatusCode ignorado, `CVTEngine.set_value` descartando quality, ausencia de hold-last en raw, alarmas sin gate, PVs no stale al disconnect OPC, Login 503 sin correlation id, ausencia de banner degradado.

**Cadena pre-fix (obsoleta):**

```
OPC datachange → (NO StatusCode) → set_value_fast(quality=GOOD) → Alarm.notify sin gate
```

### 8.2 Verificación post-spec 09 (misma fecha, supersedida por §0–7)

Cerró CA-OQ-01…08 con veredicto **B+ calidad / A− Login**. Residuales OQ-R1…R4 motivaron la spec 10; quedan cerrados en esta revisión.
