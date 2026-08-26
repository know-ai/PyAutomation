# Domain configuration (DomainConfigurable)

Product engines can expose extra configuration in `/hmi/machines/detailed` **without** modifying PyAutomationIO. The framework only duck-types three methods and renders a JSON schema.

## Contract

Implement these methods on the state machine class (do **not** add them to `StateMachineCore` unless every engine should show a domain form):

```python
def get_ui_schema(self) -> dict:
    return {
        "version": 1,
        "title": "My engine",
        "sections": [
            {
                "id": "main",
                "label": "Detection",
                "fields": [
                    {
                        "key": "gain",
                        "type": "number",
                        "label": "Gain",
                        "min": 0,
                        "max": 10,
                        "step": 0.1,
                        "unit": "adim",
                    }
                ],
            }
        ],
        "ui_hints": {
            "exclusive_subscribe_pairs": [["inlet_flow", "outlet_flow"]],
            "lock_generic_attributes": ["threshold"],
            "threshold_unit": "%",
        },
    }

def get_config(self) -> dict:
    return {"gain": self.gain}

def put_config(self, payload: dict) -> dict:
    gain = float(payload["gain"])
    if gain < 0:
        raise ValueError("gain must be >= 0")
    self.gain = gain
    # persist plant YAML / DB here
    return self.get_config()
```

Runtime detection: `automation.domain_config.supports_domain_config(machine)` (all three methods present and callable). `serialize()` includes `has_domain_config: bool`.

`put_config` must raise `ValueError` or `TypeError` on validation failure. The API maps those to HTTP 400.

## REST

| Method | Path | Behaviour |
|---|---|---|
| GET | `/api/machines/<name>/domain-config` | `{schema, config}` or **404** if the machine is missing or not DomainConfigurable |
| PUT | `/api/machines/<name>/domain-config` | body → `put_config`; 200 `{status, config}` |
| PUT | `/api/machines/<name>/attributes` | **Generic keys only**: `threshold`, `on_delay`, `interval`, `execution_interval`, `sample_interval`, `sample_overrides`, `signal_modes`, `buffer_size`. Any other key → 400 |

Auth is the same API-key session as the rest of `/machines`.

`PUT /domain-config` diffs the previous `get_config()` against the result and writes one **Events** row per changed field (`classification=Configuration`). The row stores the operator (`user`) and timestamp; the message/description say which field moved from which value to which. `_reset` and `_set_factory` also emit an action event. Engines do not implement this themselves.

## HMI

`MachinesDetailed` shows the generic attributes card when the engine has threshold/on_delay/buffer **and** `ui_hints.show_generic_attributes_card` is not `false`. Engines with a full DomainConfig slot (e.g. NPW) should set `show_generic_attributes_card: false` and move `on_delay` into their domain schema so the operator has a single configuration card.

`ui_hints` adjust the generic section (exclusive subscribe pairs, locked attributes, threshold unit, factory defaults). They are optional.

Optional schema extras (all defined by the product engine; the HMI only renders them):

- `title`: card header.
- Section `label`: visible subsection heading. Omit it to hide the heading.
- Section `hint`: informational banner (no fields required).
- Field `columns`: Bootstrap grid width 1–12 so related inputs sit on the same row.
- Field `label`: written caption. Visibility is controlled by `label_display` / `show_label`.
- Field `short_label`: compact prefix inside the input (e.g. `SS`, `N`).
- Field `help`: description. Placement is controlled by `help_display`.
- Field `read_only` / `read_only_when`: lock a control (read-only numbers render as text, without spinners).
- Field `false_label` / `true_label`: segmented boolean instead of a switch.
- `ui_hints.lock_generic_attributes`: hide/disable fields on the legacy Machine Attributes card (`threshold`, `buffer_size`, `on_delay`).
- `ui_hints.show_generic_attributes_card`: set `false` when the DomainConfig slot owns those knobs (recommended once `on_delay` lives in the domain schema).
- `ui_hints.factory_defaults`: snapshot for **Volver a valores de fábrica**. The HMI `PUT`s `{ "_reset": true }`. **Guardar** must not overwrite this snapshot.
- `ui_hints.show_set_factory`: when true (default if `factory_defaults` exist), the HMI shows **Fijar como valores de fábrica**, which `PUT`s the current form plus `{ "_set_factory": true }`. The engine must persist that snapshot separately from the live config.
- `ui_hints.label_display`: `"visible"` (default) or `"hidden"`. Overridable per section or field (`label_display` or `show_label`).
- `ui_hints.help_display`: `"text"` (default), `"tooltip"`, `"both"`, or `"none"`. Overridable per section or field.

Presentation defaults keep classic forms (visible labels + help text). A compact industrial form sets `label_display: "hidden"` and `help_display: "tooltip"` in `ui_hints` without changing PyAutomationIO.

New **widget types** or CSS outside this vocabulary still require a framework change. Layout, copy, card title, and label/tooltip policy do not.

Schema `version` greater than 1 still loads; the slot shows a warning and does not crash.

## Migration (breaking)

Domain fields such as `detection_threshold_mode` are **no longer** accepted on `PUT /attributes`. Move them into `get_ui_schema` / `put_config` on the product engine (e.g. iDetectFugas Fase B). Until then the HMI will not show those controls.

See also: [State machines](state_machines.md), `automation/domain_config.py`.
