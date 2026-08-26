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
| PUT | `/api/machines/<name>/attributes` | **Generic keys only**: `threshold`, `on_delay`, `interval`, `execution_interval`, `sample_interval`, `sample_overrides`, `buffer_size`. Any other key → 400 |

Auth is the same API-key session as the rest of `/machines`.

## HMI

`MachinesDetailed` shows the generic attributes card when the engine has threshold/on_delay/buffer. If `has_domain_config` is true it loads `/domain-config` and mounts `DomainConfigSlot`.

`ui_hints` adjust the generic section (exclusive subscribe pairs, locked attributes, threshold unit). They are optional.

Schema `version` greater than 1 still loads; the slot shows a warning and does not crash.

## Migration (breaking)

Domain fields such as `detection_threshold_mode` are **no longer** accepted on `PUT /attributes`. Move them into `get_ui_schema` / `put_config` on the product engine (e.g. iDetectFugas Fase B). Until then the HMI will not show those controls.

See also: [State machines](state_machines.md), `automation/domain_config.py`.
