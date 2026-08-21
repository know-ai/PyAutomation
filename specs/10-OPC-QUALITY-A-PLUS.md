# Documento 10: Calidad OPC UA y arranque degradado — nivel A+

<a id="top"></a>

| Campo | Valor |
|---|---|
| **Versión** | 2.0 |
| **Fecha** | 2026-08-21 |
| **Producto** | PyAutomationIO (`automation/` + HMI React) |
| **Estado** | **Implementado** (Fases 1–4 en código; soak 24 h de planta **pendiente**) |
| **Amplía** | [09-OPC-QUALITY-AND-DEGRADED-STARTUP.md](./09-OPC-QUALITY-AND-DEGRADED-STARTUP.md) (P0/P1 baseline B+) |
| **Auditoría** | [AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP.md](../audits/AUDIT_OPC_QUALITY_AND_DEGRADED_STARTUP.md) |
| **Runbook** | [opc-quality-runbook.md](../docs/opc-quality-runbook.md) |
| **Normas** | OPC UA Part 4 · ISA-18.2 · IEC 61508 (SIL-ready, no certificación) · IEC 62443 · ISO 13849 (contraste) |
| **Filosofía** | El operador nunca debe ser engañado por una señal que no refleja la realidad del proceso. |

---

## Índice

| § | Sección |
|---|---|
| 1 | [Objetivo A+](#objetivo) |
| 2 | [Principios](#principios) |
| 3 | [Arquitectura](#arquitectura) |
| 4 | [Componentes](#componentes) |
| 5 | [Fases](#fases) |
| 6 | [Criterios CA-OQ-09…15](#criterios) |
| 7 | [Veredicto](#veredicto) |

---

## 1. Objetivo A+

<a id="objetivo"></a>

Cerrar los residuales OQ-R1…R4 de la spec 09 y elevar calidad de señal de **B+** a **A−/A+**:

1. Alarma ISA-18.2 dedicada `ALM.QUALITY.<tag>` (fail-safe, independiente de proceso).
2. `event_id` visible al operador en Login 503.
3. Política UNCERTAIN configurable en Settings, aplicada en caliente (sin I/O en hot path).
4. Badge G/U/B en Trends históricos y DataLogger.
5. Subcódigo OPC (forense) en Quality + tooltip HMI.
6. Soak 24 h documentado (CA-OQ-13…15) — validación de planta.

**Fuera de alcance:** certificación SIL formal; rediseño SAF; persistir quality en cada muestra histórica del historiador (el badge de Trends usa calidad live del CVT).

---

## 2. Principios

<a id="principios"></a>

| Principio | Aplicación |
|---|---|
| **S** | `quality.py` (mapper), `quality_gate.py` (engine), `quality_alarms.py` (BOOL ISA), HMI badge/banner |
| **O** | Substatus extensible (`SensorFailure`, `Overrange`, …) sin tocar el CVT |
| **L** | Wire hot path sigue siendo `float` 1.0 / 0.5 / 0.0; `Quality` es inmutable en el borde OPC |
| **I** | Gate de proceso ≠ alarma de calidad ≠ banner BD |
| **D** | `Alarm.notify` consulta `get_inhibit_uncertain_quality()` (caché), no `app_config.json` |
| **Hot path** | O(1) por muestra; alarma de calidad lazy + fail-safe; sin `json.load` en notify |
| **Fail-safe** | BAD/stale → hold-last + inhibit proceso + `ALM.QUALITY.*` |
| **Fail-operational** | Adquisición y SAF siguen; banner degradado + Login con `event_id` |

---

## 3. Arquitectura

<a id="arquitectura"></a>

```
OPC StatusCode
  → map_opc_status() → Quality(severity, opc_code, substatus)
  → CVT.set_value_fast(..., quality, opc_code, substatus)
  → Tag: hold-last si BAD/NaN; stale; notify
  → AlarmQualityGate (caché inhibit UNCERTAIN)
  → QualityAlarmEngine → SYS.QUALITY.<tag> / ALM.QUALITY.<tag>
  → Events (Quality changed; event_id)
  → HMI: badge G/U/B + substatus; Login event_id; banner BD
```

Modelo (borde OPC; el Tag conserva float en el hot path):

```python
@dataclass(frozen=True)
class Quality:
    severity: float          # GOOD=1.0 UNCERTAIN=0.5 BAD=0.0
    opc_code: int | None
    substatus: str | None    # SensorFailure, LastUsable, Overrange, …
```

---

## 4. Componentes

<a id="componentes"></a>

| Pieza | Ruta |
|---|---|
| Quality + mapper + caché inhibit | `automation/signal_conditioning/quality.py` |
| `QualityAlarmEngine` | `automation/alarms/quality_gate.py` |
| BOOL `SYS.QUALITY.*` / `ALM.QUALITY.*` | `automation/utils/quality_alarms.py` |
| Hook hold-last / transición | `automation/tags/tag.py` |
| Settings API | `automation/modules/settings/resources/settings.py` |
| Login `event_id` HMI | `hmi/src/pages/Login.tsx`, `DatabaseConfigForm.tsx` |
| Toggle UNCERTAIN | `hmi/src/components/QualityPolicyPanel.tsx` |
| Trends / DataLogger | `hmi/src/components/HistoricalQualityLegend.tsx` |

---

## 5. Fases

<a id="fases"></a>

| Fase | Entregable | Prioridad | Estado |
|---|---|---|---|
| 1 | `QualityAlarmEngine` + `ALM.QUALITY.<tag>` | P0 | **Implementado** |
| 2 | `event_id` en Login / DatabaseConfigForm | P0 | **Implementado** |
| 3 | Toggle `alarm_inhibit_uncertain_quality` | P1 | **Implementado** |
| 4 | Badge en Trends históricos y DataLogger | P1 | **Implementado** |
| 5 | Soak 24 h planta (CA-OQ-13…15) | P0 validación | Procedimiento en runbook |
| 6 | Runbook operador | P2 | `docs/opc-quality-runbook.md` |

---

## 6. Criterios de aceptación

<a id="criterios"></a>

| ID | Criterio |
|---|---|
| CA-OQ-09 | `ALM.QUALITY.<tag>` se activa en BAD/stale y se desactiva en GOOD |
| CA-OQ-10 | Login 503: HMI muestra `event_id` en DatabaseConfigForm |
| CA-OQ-11 | Toggle UNCERTAIN en Settings aplica en caliente (caché, sin reiniciar) |
| CA-OQ-12 | Trends históricos y DataLogger muestran badge G/U/B (live) o «sin calidad» |
| CA-OQ-13 | Soak: sensor BAD intermitente → alarmas de calidad correctas; proceso inhibido |
| CA-OQ-14 | Soak: pérdida/reconexión OPC → stale/BAD → `ALM.QUALITY.*` |
| CA-OQ-15 | Soak: BD 30 min down → banner + Login `event_id` + SAF flush al recuperar |

Tests: `automation/tests/test_opc_quality.py` (09–11), revisión estática HMI (10, 12). Soak: [opc-quality-runbook.md](../docs/opc-quality-runbook.md) § Soak.

---

## 7. Veredicto objetivo

<a id="veredicto"></a>

| Dimensión | Post-spec 09 | Meta 10 | Cómo se alcanza A+ |
|---|---|---|---|
| Calidad de señal | **B+** | **A− / A+** | `ALM.QUALITY.*` + substatus + Settings + soak planta |
| Login / UX degradada | **A−** | **A** | `event_id` visible al operador |
| Disponibilidad | **A−** | Mantener | Sin I/O de config en hot path |

**A+ pleno** queda condicionado al soak 24 h (CA-OQ-13…15) en planta o laboratorio.
