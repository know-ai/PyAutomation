# AUDIT_HMI_MACHINE_DOMAIN_EXTENSION — Neutralidad de PyAutomationIO frente a productos de dominio

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO (`github/PyAutomation`, paquete `automation` + HMI `hmi/src/`) |
| **Versión auditada** | 2.8.1 → contrato DomainConfigurable implementado en árbol 2026-08-26 |
| **Pregunta fundamental** | ¿Puede un proyecto externo (p. ej. iDetectFugas) añadir formularios de configuración complejos a `/hmi/machines/detailed` **sin modificar una sola línea** de PyAutomationIO? |
| **Respuesta (pre Fase A)** | **NO** (inventario §3) |
| **Respuesta (post Fase A)** | **SÍ** — Schema-Driven UI + duck-typing; ver [§13 evidencia](#13-evidencia-de-implementación-2026-08-26) |
| **Principios (pre)** | DIP / OCP violados |
| **Principios (post)** | Host de schemas; el producto implementa `get_ui_schema` / `get_config` / `put_config` |
| **Fecha** | 2026-08-26 (auditoría) · implementación 2026-08-26 |
| **Complementa** | [AUDIT_STATE_MACHINES.md](./AUDIT_STATE_MACHINES.md), [AUDIT_HMI.md](./AUDIT_HMI.md); producto: `idetectfugas/audits/10-AUDIT_HMI_MACHINE_CONFIG_EXTENSION.md` |
| **Misión** | Evolucionar PyAutomationIO de un framework que **conoce** iDetectFugas a uno que **ignora** el dominio, pero es extraordinariamente extensible |

---

## Índice

1. [Veredicto y pregunta fundamental](#1-veredicto-y-pregunta-fundamental)
2. [Arquitectura genérica esperada vs filtraciones](#2-arquitectura-genérica-esperada-vs-filtraciones)
3. [Inventario exhaustivo de acoplamientos](#3-inventario-exhaustivo-de-acoplamientos)
4. [Anti-patrones de diseño](#4-anti-patrones-de-diseño)
5. [Flujo actual (cómo pide y guarda config la UI)](#5-flujo-actual-cómo-pide-y-guarda-config-la-ui)
6. [Por qué la respuesta es NO](#6-por-qué-la-respuesta-es-no)
7. [Contrato objetivo: Schema-Driven UI](#7-contrato-objetivo-schema-driven-ui)
8. [Neutralidad de `serialize()`](#8-neutralidad-de-serialize)
9. [Test de regresión negativa](#9-test-de-regresión-negativa)
10. [Plan de migración Fase A (PyAutomationIO)](#10-plan-de-migración-fase-a-pyautomationio)
11. [Criterios de aceptación (Definition of Done)](#11-criterios-de-aceptación-definition-of-done)
12. [Fuera de alcance / Fase B](#12-fuera-de-alcance--fase-b)
13. [Evidencia de implementación (2026-08-26)](#13-evidencia-de-implementación-2026-08-26)

---

## 1. Veredicto y pregunta fundamental

> ¿Puede un proyecto externo añadir formularios de configuración complejos a la pantalla de detalle de máquinas **sin modificar** el código base de PyAutomationIO?

| Pre Fase A | Post Fase A (este árbol) |
|---|---|
| **NO** | **SÍ** |

**Por qué era NO:** la HMI y `PUT .../attributes` ramificaban por nombres de motores de producto. Inventario histórico en §3.

**Por qué es SÍ ahora:** un engine externo implementa `get_ui_schema` / `get_config` / `put_config`. El framework los detecta por duck-typing, publica `has_domain_config` en `serialize()`, sirve `GET|PUT /api/machines/<name>/domain-config` y renderiza `DomainConfigSlot`. Cero nombres de producto en la API/HMI de machines (guardia en `test_machine_domain_config.py`).

**Hueco de producto:** hasta que iDetectFugas implemente el Protocol (Fase B), el slot no aparece y el toggle probabilidad/estadístico deja de existir en HMI.

---

## 2. Arquitectura genérica esperada vs filtraciones

### 2.1 Lo que el framework debería hacer (capa genérica)

| Capa | Responsabilidad universal |
|---|---|
| `AutomationStateMachine` / workers | Ciclo SM, timings (`execution_interval`, `sample_interval`), buffers, subscribe |
| `PUT /api/machines/<name>/attributes` | `threshold`, `on_delay`, `buffer_size`, intervals, overrides — **solo genéricos** |
| `GET /api/machines/<name>` | Metadatos universales + process vars tipadas |
| HMI `/hmi/machines/detailed` | Inputs genéricos + transitions (reset/restart/…) |
| Transiciones | Independientes del dominio de fuga |

### 2.2 Lo que filtra dominio de producto (contaminación)

| Síntoma | Dónde |
|---|---|
| Campos API documentados como “Solo PPA/NPW” | `machines.py` model + docstring PUT |
| Clamp 0–100 + `wavelet.threshold_iqr` si `name == "npw"` | `machines.py`, `state_machine.py` (carga BD), Dash legado |
| UI que adivina unidades / locks / pares de tags por substring del nombre | `MachinesDetailed.tsx` |
| Card de atributos gated por `classification.includes("leak detection")` | `MachinesDetailed.tsx` |
| Cliente TS tipa `detection_threshold_mode` en el mismo PUT genérico | `machines.ts` |

`workers/state_machine.py`: **sin** hardcodes de nombres de motores de fuga (limpio en este eje).

---

## 3. Inventario exhaustivo de acoplamientos

Convención de severidad:

| Severidad | Significado |
|---|---|
| **P0** | Bloquea DIP/OCP; debe salir en Fase A |
| **P1** | Contaminación en legado Dash / comentarios / tipado TS; limpiar en el mismo sprint o inmediatamente después |
| **P2** | Duck-typing genérico aceptable *si* se mueve a `/domain-config` y se retira el nombre de producto de mensajes/docs |

### 3.1 Backend — `automation/modules/machines/resources/machines.py`

| ID | Archivo:línea | Severidad | Descripción |
|---|---|---|---|
| BE-DC-01 | `machines.py:99-102` | **P0** | Modelo Flask-RESTx `detection_threshold_mode` documentado como *“PPA/NPW only”* — el contrato público del framework nombra productos. |
| BE-DC-02 | `machines.py:575,587-592` | **P0** | Docstring PUT: “Solo PPA/NPW”, persistencia YAML, “otras máquinas NPW legacy”. |
| BE-DC-03 | `machines.py:613,624-630` | **P0** | `detection_threshold_mode` forma parte del contrato de `/attributes` (validación “al menos un atributo”). |
| BE-DC-04 | `machines.py:648-670` | **P0**/P2 | Rama de modo umbral. El `hasattr(set_detection_threshold_mode_from_ui)` es duck-typing usable, pero el **mensaje 400** dice *“only supported for PPA/NPW engines”* — fuga de dominio en la API. |
| BE-DC-05 | `machines.py:677-691` | **P2→mover** | `set_active_detection_threshold_from_ui` — duck-typing OK como puente, pero vive en `/attributes` sobrecargado; debe migrar a `/domain-config`. |
| BE-DC-06 | `machines.py:693-702` | **P0** | Hardcode explícito: `"leak detection" in classification` **y** `machine_name.lower() == "npw"` → clamp 0–100 + `machine.wavelet.threshold_iqr = threshold_value`. El framework **parsea JSON sabiendo que existe NPW**. |
| BE-DC-07 | `machines.py:873-880` | **P1** | Tras persistir, llama `_load_bayesian_motor_thresholds` / `_sync_bayesian_detection_threshold` por nombre de método bayesiano — acoplamiento semántico a iDetectFugas (aunque sea duck-typing). Debe vivir solo tras `put_config` del producto. |

### 3.2 Backend — `automation/state_machine.py` (carga de config BD)

| ID | Archivo:línea | Severidad | Descripción |
|---|---|---|---|
| BE-DC-08 | `state_machine.py:279-280` | P1 | Comentario: “módulos (p.ej. NPW/Observer)”. |
| BE-DC-09 | `state_machine.py:294-298` | **P0** | Al hidratar threshold desde BD: si classification contiene `"leak detection"` y `name == "npw"` → escribe `machine.wavelet.threshold_iqr`. Contaminación en el core SM, no solo en la API. |
| BE-DC-10 | `state_machine.py:870-872` | P1 | Comentario `_legacy_sample_and_execute`: “iDetectFugas (LDS/NPW)”. Sin rama ejecutable por nombre; limpiar wording. |
| BE-DC-11 | `state_machine.py:1636-1638` | P1 | Comentario `on_enter_waiting`: “Leak engines…”. |

**Nota:** `serialize()` base (`state_machine.py:1547-1566`) es **genérico** (state, actions, intervals, models). Los flags de dominio (`supports_detection_threshold_mode`, `active_detection_threshold`, etc.) los **añade el producto** al sobrescribir `serialize()` / `get_serialized_models()` — eso es aceptable. El problema es que la **HMI del framework interpreta** esos flags *y además* hardcodea nombres.

### 3.3 Backend — legado Dash (aún en árbol)

| ID | Archivo:línea | Severidad | Descripción |
|---|---|---|---|
| BE-DC-12 | `pages/components/machines.py:46-49` | **P0** (legado) | `if "pfm" in machine_name` / `observer` → `disable = True` en formulario de atributos. |
| BE-DC-13 | `pages/callbacks/machines_detailed.py:145-148` | **P0** (legado) | Misma lógica pfm/observer. |
| BE-DC-14 | `pages/callbacks/machines_detailed.py:534-549` | **P0** (legado) | `leak detection` + `npw` → clamp + `wavelet.threshold_iqr`. |

Aunque Dash no sea el path de producto actual, **sigue siendo código base** que viola DIP. Fase A debe neutralizarlo o marcarlo deprecated y eliminar ramas.

### 3.4 Backend — otros

| ID | Archivo:línea | Severidad | Descripción |
|---|---|---|---|
| BE-DC-15 | `tags/tag.py:938-949` | P2 | `_machine_threshold_value` usa `get_active_detection_threshold` (duck-typing). Comentario menciona PPA/NPW. Aceptable si el getter es contrato opcional genérico; retirar nombres de producto del docstring. |
| BE-DC-16 | `workers/state_machine.py` | — | **Sin** hardcodes npw/ppa/lds. OK. |

### 3.5 Frontend — `hmi/src/pages/MachinesDetailed.tsx`

| ID | Archivo:línea | Severidad | Descripción |
|---|---|---|---|
| FE-DC-01 | `MachinesDetailed.tsx:86-90` | **P0** | `name.includes("lds")` → pares exclusivos flow+density; `pfm`/`observer` → solo density. UI adivina por id. |
| FE-DC-02 | `MachinesDetailed.tsx:118-126` | **P0** | `name === "ppa" \|\| name === "npw"` (o flag) → unidades de modo probabilidad/estadístico. |
| FE-DC-03 | `MachinesDetailed.tsx:128-148` | **P0** | `observer` → unidad leak_flow; `pfm` → %. |
| FE-DC-04 | `MachinesDetailed.tsx:196` | **P0** | Tipo de atributo incluye `detection_threshold_mode` en el flujo genérico de confirmación. |
| FE-DC-05 | `MachinesDetailed.tsx:204-206` | **P0** | `supportsDetectionThresholdMode`: hardcode `ppa`/`npw` **además** del flag serialize. |
| FE-DC-06 | `MachinesDetailed.tsx:211,421,456-476,484,503,777,823` | **P0** | Lectura/escritura de `detection_threshold_mode` / `active_detection_threshold` vía `/attributes`. |
| FE-DC-07 | `MachinesDetailed.tsx:377,626,697,1543-1547` | **P0** | Locks de threshold/buffer/on_delay si nombre ∈ `{pfm, observer}`. |
| FE-DC-08 | `MachinesDetailed.tsx:1914-1918` | **P0** | Card “Machine Attributes” solo si `classification.includes("leak detection")`. El framework decide qué es “leak detection”. |
| FE-DC-09 | `MachinesDetailed.tsx:1968-1982` | **P0** | Select de modo umbral en JSX condicionado al dominio. |

### 3.6 Frontend — servicios / utils

| ID | Archivo:línea | Severidad | Descripción |
|---|---|---|---|
| FE-DC-10 | `services/machines.ts:104-116` | **P0** | `updateMachineAttributes` tipa `detection_threshold_mode` en el cliente genérico. No hay `fetchNpwConfig` (bien), pero el campo de dominio está en el API client universal. |
| FE-DC-11 | `utils/tagThreshold.ts:29` | P2 | Prefiere `active_detection_threshold` en serialize de lista — OK si el producto lo publica; no hardcodea nombres. |

### 3.7 Resumen cuantitativo

| Zona | Hallazgos P0 | P1 | P2 |
|---|---|---|---|
| API machines | 6 | 1 | 1 |
| state_machine core | 1 | 3 | 0 |
| Dash legado | 3 | 0 | 0 |
| HMI React | 9 | 0 | 0 |
| services/utils | 1 | 0 | 1 |
| **Total** | **~20 P0** | **4** | **2** |

---

## 4. Anti-patrones de diseño

### 4.1 Violación DIP

La capa de alto nivel (HMI + API machines) **depende de detalles de un producto concreto** (nombres de motores iDetectFugas). Debería depender de una **abstracción** (`DomainConfigurable` / schema).

```
Hoy:     HMI ──conoce──► "npw" | "lds" | "pfm" | "leak detection"
Objetivo: HMI ──consume──► ui_schema()  ◄──implementa──  iDetectFugas engines
```

### 4.2 Violación OCP

- **Abierto a modificación:** cada motor nuevo (o rename `NPW` → `Linea1.NPW`) obliga a tocar `MachinesDetailed.tsx` / `machines.py`.
- **Cerrado a extensión:** no hay registry, slot ni endpoint de dominio. No se puede “enchufar” un form sin PR al framework.

### 4.3 Responsabilidad conjunta en `/attributes`

El mismo PUT mezcla:

1. Config **universal** (interval, buffer, on_delay, threshold plano).
2. Config **de dominio** (`detection_threshold_mode`, side-effects wavelet/Bayes).

Eso impide evolucionar el producto sin riesgo de romper la UI genérica, y viceversa.

### 4.4 Falta de tipado declarativo

La UI **adivina** (slider vs select vs unidad) por substring del nombre. El backend no publica un schema de inputs. Resultado: hardcodes FE-DC-01…03.

---

## 5. Flujo actual (cómo pide y guarda config la UI)

```
┌─ Navegador /hmi/machines/detailed ──────────────────────────────┐
│  MachinesDetailed.tsx                                            │
│   • if name includes lds|pfm|observer → pares / locks / units    │
│   • if classification includes "leak detection" → card atributos │
│   • if ppa|npw → select detection_threshold_mode                 │
└───────────────┬───────────────────────────────┬─────────────────┘
                │ GET /api/machines/<name>      │ PUT /api/machines/<name>/attributes
                │                               │  { threshold, on_delay, buffer_size,
                │                               │    detection_threshold_mode, … }
                ▼                               ▼
┌─ machines.py ───────────────────────────────────────────────────┐
│  serialize() genérico + campos que el engine aporte              │
│  PUT:                                                            │
│   • duck-typing set_*_from_ui                                    │
│   • if classification leak + name==npw → wavelet.threshold_iqr   │
│   • persist_ui_config_attributes + sync bayesiano                │
└───────────────┬─────────────────────────────────────────────────┘
                ▼
┌─ Engines iDetectFugas (fuera del repo, pero implícitos) ────────┐
│  YAML planta · Bayes · classic engines                           │
└──────────────────────────────────────────────────────────────────┘
```

**Problema:** el flujo “genérico” ya contiene ramas que solo tienen sentido si el proceso carga motores LDS. Un `GenericMotor` sin esos métodos aún puede ser discriminado por nombre vacío, pero la **card** y los **pares** dependen de classification/nombre de producto.

---

## 6. Por qué la respuesta es NO

Para que un producto externo añada un formulario complejo **sin tocar PyAutomationIO** haría falta al menos uno de:

1. Un **slot** en la HMI que renderice un schema remoto, o  
2. Un **endpoint** de dominio + componente dinámico ya existente en el wheel.

**Ninguno existe hoy.** Las únicas vías reales son:

| Vía | ¿Modifica PyAutomationIO? |
|---|---|
| Nuevo hardcode en `MachinesDetailed.tsx` | **Sí** |
| Nueva rama en `PUT .../attributes` | **Sí** |
| Fork del wheel / patch site-packages | **Sí** (y prohibido en operación) |
| Solo YAML + REST propio fuera de `/hmi/machines/detailed` | No modifica framework, pero **no embebe** en la vista pedida |

Por tanto: **embeber forms de dominio en machines/detailed sin tocar el framework = imposible con el código actual.**

---

## 7. Contrato objetivo: Schema-Driven UI

PyAutomationIO se convierte en **host**. El producto implementa el contrato. Cero nombres de motores en el framework.

### 7.A Interfaz duck-typing (opcional en engines)

Vivir como protocolo documentado (ABC opcional o solo duck-typing). **No** importar iDetectFugas.

```python
# Conceptual — documentación / typing Protocol en PyAutomationIO
class DomainConfigurable:
    def get_ui_schema(self) -> dict:
        """JSON Schema simplificado: number | select | boolean | string | object | array."""
        ...

    def get_config(self) -> dict:
        """Valores actuales alineados a keys del schema."""
        ...

    def put_config(self, payload: dict) -> dict:
        """Valida, aplica en caliente, persiste. Retorna config efectiva (+ warnings)."""
        ...
```

Helper sugerido en el resource:

```python
def _domain_configurable(machine):
    return all(
        callable(getattr(machine, name, None))
        for name in ("get_ui_schema", "get_config", "put_config")
    )
```

### 7.B Endpoints desacoplados (no tocar el contrato estable de `/attributes` más que para **eliminar** campos de dominio)

| Método | Ruta | Comportamiento |
|---|---|---|
| `GET` | `/api/machines/<name>/domain-config` | Si `_domain_configurable` → `{ "schema": get_ui_schema(), "config": get_config() }`. Si no → **404** o `{ "supported": false }` (elegir uno y documentarlo; preferencia: **404** limpio para GenericMotor). |
| `PUT` | `/api/machines/<name>/domain-config` | Body → `put_config`; 400 validación; 200 config efectiva. |
| `PUT` | `/api/machines/<name>/attributes` | **Solo** genéricos. Rechazar `detection_threshold_mode` (y cualquier key no whitelist) con **400**. |

Whitelist sugerida de `/attributes` post-Fase A:

`threshold`, `interval`, `execution_interval`, `sample_interval`, `sample_overrides`, `buffer_size`, `on_delay`.

### 7.C Ejemplo JSON de schema (producto; el framework solo lo renderiza)

```json
{
  "version": 1,
  "title": "NPW",
  "sections": [
    {
      "id": "detection",
      "label": "Detection",
      "fields": [
        {
          "key": "detection_threshold_mode",
          "type": "select",
          "label": "Threshold mode",
          "options": [
            { "value": "probability", "label": "Probability (%)" },
            { "value": "statistic", "label": "Statistic (adim)" }
          ]
        },
        {
          "key": "active_detection_threshold",
          "type": "number",
          "label": "Active threshold",
          "min": 0,
          "depends_on": { "field": "detection_threshold_mode", "equals": "probability" },
          "unit": "%"
        },
        {
          "key": "wavelet.threshold_iqr",
          "type": "number",
          "label": "Wavelet IQR",
          "min": 0,
          "unit": "adim"
        }
      ]
    }
  ],
  "ui_hints": {
    "exclusive_subscribe_pairs": [],
    "lock_generic_attributes": []
  }
}
```

Hints genéricos (reemplazan hardcodes FE):

| Hint | Sustituye |
|---|---|
| `exclusive_subscribe_pairs` | FE-DC-01 (lds/pfm density pairs) |
| `lock_generic_attributes: ["threshold","buffer_size","on_delay"]` | FE-DC-07 (pfm/observer locks) |
| `show_generic_attributes_card: true` | FE-DC-08 (leak detection gate) — o simplemente: mostrar card genérica siempre que existan threshold/on_delay en el engine |
| `threshold_unit` / fields[].unit | FE-DC-02/03 |

### 7.D Componente React `DomainConfigSlot`

- Props: `machineName`.
- `GET domain-config` → si 404, render `null`.
- Render dinámico: `number` | `boolean` | `select` | `string` | nested `object`/`array` (MVP: number/boolean/select/string).
- Respeta `depends_on`, `min`/`max`, `unit` inline.
- `PUT` al guardar; toasts del design system HMI existente (Bootstrap/AdminLTE del proyecto — **no** introducir MUI solo por esto).
- **Cero** `if (name.includes("npw"))`.

---

## 8. Neutralidad de `serialize()`

### 8.1 Hoy (contaminación efectiva vía consumidores)

Aunque el `serialize()` base sea limpio, la HMI trata como API estable:

- `supports_detection_threshold_mode`
- `active_detection_threshold`
- `detection_threshold_mode`
- `classification === "…leak detection…"`

### 8.2 Objetivo (framework)

Campos que el framework garantiza / documenta como estables:

```json
{
  "name": "GenericMotor",
  "state": "running",
  "actions": ["…"],
  "execution_interval": 1.0,
  "sample_interval": null,
  "sample_overrides": {},
  "threshold": { "value": 0.5, "unit": "%" },
  "on_delay": { "value": 5 },
  "buffer_size": { "value": 60 },
  "classification": "Custom",
  "has_domain_config": false
}
```

`has_domain_config` = resultado de `_domain_configurable(machine)` (calculado en el resource al listar/detallar, **no** requiere que el engine lo ponga a mano).

Todo lo demás de dominio **solo** vía `GET /domain-config`.

### 8.3 Producto (iDetectFugas, fuera de este repo)

Puede seguir enriqueciendo su propio `serialize()` para Socket.IO / tags, pero la HMI **core** no debe ramificar por esos campos. El slot solo mira `has_domain_config` + `/domain-config`.

---

## 9. Test de regresión negativa

Propuesta: `automation/tests/test_machine_domain_config_neutrality.py`

```python
"""CA-DC-NEUTRAL: framework must not special-case product engine names."""

def test_generic_motor_attributes_reject_detection_threshold_mode(client, auth):
    # Arrange: register AutomationStateMachine subclass named "GenericMotor"
    # (no get_ui_schema / put_config / set_detection_threshold_mode_from_ui)
    r = client.put(
        "/api/machines/GenericMotor/attributes",
        json={"detection_threshold_mode": "probability"},
        headers=auth,
    )
    assert r.status_code == 400
    body = r.get_json()
    assert "detection_threshold_mode" in body["message"].lower() or "unknown" in body["message"].lower()
    assert "ppa" not in body["message"].lower()
    assert "npw" not in body["message"].lower()


def test_generic_motor_domain_config_unsupported(client, auth):
    r = client.get("/api/machines/GenericMotor/domain-config", headers=auth)
    assert r.status_code == 404  # or supported:false — pick one in implementation


def test_serialize_has_domain_config_false(client, auth):
    r = client.get("/api/machines/GenericMotor", headers=auth)
    ser = r.get_json()["serialization"]  # shape according to real response
    assert ser.get("has_domain_config") is False


def test_no_product_engine_name_branches_in_machines_module():
    """Static guard — fail CI if npw/ppa/lds/pfm/observer leak into machines resource."""
    from pathlib import Path
    text = Path("automation/modules/machines/resources/machines.py").read_text().lower()
    for token in ("npw", "ppa", "lds", "pfm", "observer", "leak detection"):
        assert token not in text, f"product token {token!r} found in machines API"
```

HMI (opcional e2e / unit del slot): con máquina sin domain-config, **no** montar inputs wavelet ni select de modo.

---

## 10. Plan de migración Fase A (PyAutomationIO)

Objetivo de sprint: **la rama `dev` de PyAutomationIO no tiene menciones de `npw`, `ppa`, `lds`, `pfm`, `observer` ni `leak detection` en la lógica de negocio/UI core de machines.**

### 10.1 Archivos a tocar

| Archivo | Acción |
|---|---|
| `automation/modules/machines/resources/machines.py` | Añadir resource `domain-config`; whitelist `/attributes`; eliminar BE-DC-01…07 hardcodes/mensajes de producto |
| `automation/state_machine.py` | Eliminar BE-DC-09 (wavelet/npw en hydrate); opcional hook genérico `machine.apply_persisted_threshold(value)` duck-typing |
| `hmi/src/pages/MachinesDetailed.tsx` | Quitar FE-DC-01…09; integrar `DomainConfigSlot`; card genérica sin gate leak; locks/pares desde `ui_hints` o schema |
| `hmi/src/services/machines.ts` | Quitar `detection_threshold_mode` de attributes; añadir `getDomainConfig` / `putDomainConfig` |
| `hmi/src/components/DomainConfigSlot.tsx` | **Nuevo** — renderer schema |
| `automation/pages/components/machines.py` | Neutralizar o deprecar hardcodes pfm/observer |
| `automation/pages/callbacks/machines_detailed.py` | Neutralizar BE-DC-13/14 |
| `automation/tags/tag.py` | Docstring neutro (BE-DC-15) |
| `automation/tests/test_machine_domain_config_neutrality.py` | **Nuevo** |
| `docs/Developments_Guide/…` | Documentar Protocol DomainConfigurable |

### 10.2 Qué deprecar

| Ítem | Estrategia |
|---|---|
| `detection_threshold_mode` en `/attributes` | **Eliminar** del model (breaking para clientes que lo usen). Coordinar release con iDetectFugas Fase B el mismo tren, o window: aceptar el key una release con `DeprecationWarning`/header y log, luego 400. Preferencia auditoría: **corte limpio en minor 2.9** + bump simultáneo producto. |
| Flags HMI que leen `supports_detection_threshold_mode` desde serialize para UI core | Dejar de usar en MachinesDetailed; el slot usa schema |
| Comentarios con nombres de producto | Reescribir a lenguaje genérico |

### 10.3 Qué lógica eliminar (checklist grep)

Tras el PR, estos comandos deben devolver **vacío** (salvo tests que aserten ausencia, docs de migración, o este audit):

```bash
rg -i 'npw|ppa|\blds\b|pfm|observer|leak detection' \
  automation/modules/machines/ \
  hmi/src/pages/MachinesDetailed.tsx \
  hmi/src/services/machines.ts \
  automation/pages/components/machines.py \
  automation/pages/callbacks/machines_detailed.py
```

Excepción permitida temporal: este archivo `audits/AUDIT_HMI_MACHINE_DOMAIN_EXTENSION.md` y changelogs.

### 10.4 Orden de implementación sugerido

1. Endpoints `/domain-config` + tests neutralidad (aún sin UI).
2. Whitelist `/attributes` + borrar rama npw/wavelet + hydrate state_machine.
3. `DomainConfigSlot` + cableado en MachinesDetailed.
4. Purge hardcodes FE + Dash.
5. Guard CI `rg` + release notes 2.9.x.
6. Coordinar iDetectFugas Fase B (implementar `get_ui_schema`/`get_config`/`put_config` en motores) **en el mismo tren de release** para no dejar hueco UX.

---

## 11. Criterios de aceptación (Definition of Done)

- [x] Pregunta fundamental → **SÍ** para un engine externo que implemente el Protocol (`ConfigurableMotor` en tests).
- [x] `rg` de tokens de producto en paths de §10.3 → vacío (`TestNoProductEngineNameBranches`).
- [x] `GenericMotor` + PUT `detection_threshold_mode` → **400** sin mencionar PPA/NPW.
- [x] `GenericMotor` + GET `domain-config` → 404; HMI no monta slot si no hay schema.
- [x] Engine con Protocol → GET/PUT domain-config round-trip (test de resource).
- [ ] DAQ / OPCUAServer sin regresión visual en detailed (verificación HMI manual / planta).
- [x] Ningún nuevo `if (name.includes(...))` de producto en HMI core.

---

## 12. Fuera de alcance / Fase B

| Ítem | Repo |
|---|---|
| Schemas reales LDS/NPW/PPA/PFM/Observer | **iDetectFugas** |
| Persistencia YAML Bayes / classic configs | **iDetectFugas** |
| Panel rico de aportes bayesianos (charts) | iDetectFugas (extensión remota opcional post-slot) |
| Editar site-packages en edge | **Prohibido** |

Documento hermano de producto: `gitlab/intelcon/idetectfugas/audits/10-AUDIT_HMI_MACHINE_CONFIG_EXTENSION.md`.

---

## Apéndice A — Mapeo hallazgo → acción

| ID | Acción Fase A |
|---|---|
| BE-DC-01…03 | Quitar del model `/attributes`; vivir en domain-config del producto |
| BE-DC-04…05 | Mover a PUT domain-config; mensajes API sin nombres de motor |
| BE-DC-06, BE-DC-09, BE-DC-14 | **Eliminar**; producto aplica wavelet en `put_config` / hydrate propio |
| BE-DC-07 | No invocar sync bayesiano desde framework; producto en `put_config` |
| BE-DC-12…13 | Locks vía `ui_hints` o atributos read_only del engine |
| FE-DC-01…09 | Sustituir por DomainConfigSlot + hints |
| FE-DC-10 | API client domain-config |

## Apéndice B — Diagrama objetivo

```
MachinesDetailed
  ├── GenericSection  →  PUT /attributes   (whitelist universal)
  └── DomainConfigSlot
        ├── GET  /domain-config  →  get_ui_schema + get_config   ⎤
        └── PUT  /domain-config  →  put_config                    ⎦ solo si el engine implementa el Protocol
                                                                    (código 100% en el proyecto externo)
```

**Cierre histórico (§1–12):** el inventario describe el acoplamiento **antes** de Fase A.

---

## 13. Evidencia de implementación (2026-08-26)

Fase A está en el árbol. PyAutomationIO **ignora** nombres de producto y hospeda schemas.

### 13.1 Archivos nuevos

| Archivo | Rol |
|---|---|
| `automation/domain_config.py` | `DomainConfigurable` Protocol, `supports_domain_config`, `GENERIC_ATTRIBUTE_KEYS`, `SCHEMA_VERSION_SUPPORTED = 1` |
| `hmi/src/components/DomainConfigSlot.tsx` | Renderer schema-driven (number/select/boolean/string; object anidado; array JSON; `depends_on`) |
| `automation/tests/test_machine_domain_config.py` | GenericMotor / ConfigurableMotor / 400 attributes / guardia estática |
| `docs/Developments_Guide/core/domain_config.md` | Guía de desarrolladores |

### 13.2 API implementada

- `GET /api/machines/<name>/domain-config` → `{schema, config}` o **404** (`MachineDomainConfigResource` en `machines.py`).
- `PUT /api/machines/<name>/domain-config` → `put_config`; `ValueError`/`TypeError` → 400; 200 `{status, config}`.
- `PUT /api/machines/<name>/attributes` rechaza keys fuera de `{threshold, on_delay, interval, execution_interval, sample_interval, sample_overrides, buffer_size}` con 400 **sin** nombres de producto.
- `StateMachineCore.serialize()` incluye `has_domain_config`.

### 13.3 HMI

- `MachinesDetailed.tsx` ya no ramifica por nombre/classification de producto.
- Card genérica si hay threshold/on_delay/buffer; locks y pares exclusivos desde `ui_hints`.
- `DomainConfigSlot` se monta cuando hay schema cargado (`has_domain_config` → GET domain-config).
- Cliente: `getMachineDomainConfig` / `putMachineDomainConfig` en `hmi/src/services/machines.ts`.

### 13.4 Hallazgos cerrados

| ID | Estado | Evidencia |
|---|---|---|
| BE-DC-01…03 | Cerrado | `detection_threshold_mode` eliminado del model Flask-RESTx y del PUT |
| BE-DC-04…05 | Cerrado | Ramas `set_*_from_ui` y mensajes PPA/NPW eliminadas de `/attributes` |
| BE-DC-06 | Cerrado | Rama `"leak detection"` + `name == npw` + `wavelet.threshold_iqr` eliminada |
| BE-DC-07 | Cerrado | Sync bayesiano ya no se invoca desde el framework |
| BE-DC-08, BE-DC-10, BE-DC-11 | Cerrado | Comentarios reescritos a lenguaje genérico |
| BE-DC-09 | Cerrado | Hydrate BD: if NPW/wavelet eliminado; hook opcional genérico `apply_persisted_threshold` |
| BE-DC-12…14 | Cerrado | Dash sin `pfm`/`observer`/`npw`/`leak detection` |
| BE-DC-15 | Cerrado | Docstring de `_machine_threshold_value` neutro |
| FE-DC-01…09 | Cerrado | Hardcodes HMI sustituidos por hints + slot |
| FE-DC-10 | Cerrado | `detection_threshold_mode` fuera de `updateMachineAttributes` |

### 13.5 Tests (PASS)

`python -m unittest automation.tests.test_machine_domain_config -v` — 10 tests OK, incluyendo:

- `has_domain_config` false/true
- PUT attributes con `detection_threshold_mode` → 400 sin `ppa`/`npw`
- GET/PUT domain-config round-trip + `ValueError` → 400
- Guardia estática sobre paths de §10.3

### 13.6 Hueco restante (Fase B, fuera de este repo)

iDetectFugas debe implementar el Protocol en LDS/NPW/PPA/PFM/Observer. Hasta entonces el slot no aparece y se pierde el toggle de modo umbral en HMI. Coordinar wheel 2.9 con esa Fase B.

