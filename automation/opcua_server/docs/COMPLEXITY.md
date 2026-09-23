# Complejidad del servidor OPC UA embebido

Autoridad: SPEC-OPCUA-SERVER-REFACTOR.

- Tick (`while_running` → `process_one_tick`): O(B + K). B = 200 exposes / 50 ms. K = dirty set, tope 1000 por tick.
- `create_tag` / `create_alarm` / `append_machine`: el hook OPC es O(1) (`enqueue_expose`). El resto de `create_tag` no forma parte de este contrato.
- Arranque y `reconcile_full`: O(N + M + E), cada 60 ticks. `AUTOMATION_OPCUA_CONSTANT_MODE=true` lo apaga y deja un watchdog rotativo de 200 tags.
- Reset: `dict.clear()` / `deque.clear()`.
- Access level: un SELECT para N ≤ 5000 (`read_by_namespaces`). Properties heredan el nivel del padre.
- Write-back: una subscription compartida.
- El tick no consulta la base de datos. `tracemalloc` en CPython no cabe en 1 KB por el `sorted()` del dirty set; el tope de prueba es 64 KB y el tick no hace I/O.
