# Arquitectura multi-edge

PyAutomation opera en modo multi-edge por defecto. Cada instancia de adquisición es un nodo con identidad propia. La API y el HMI permanecen disponibles si falta configuración; la hidratación y la adquisición se bloquean (fail-closed) hasta que existan `NODE_ID` y `AREA`.

## Variables obligatorias

| Variable | Obligatorio | Default | Rol |
|---|---|---|---|
| `AUTOMATION_MULTI_EDGE_ENABLED` | No | `true` | Activa partición, single-writer y fail-closed. `false` restaura el modo monolítico. |
| `AUTOMATION_NODE_ID` | Sí (si multi-edge está activo) | — | Identidad estable del edge. Máximo 64 caracteres. |
| `AUTOMATION_AREA` | Sí (si multi-edge está activo) | — | Clave ISA-95 de partición (`Linea1`, `Linea2`, …). |
| `AUTOMATION_SITE` | No | — | Sitio opcional para trazabilidad. |
| `AUTOMATION_SEGMENT` | Compatibilidad | — | Solo se usa como `AREA` si `AUTOMATION_AREA` está vacío. |

Los nombres de tags y alarmas de runtime deben cualificarse con el área: `Linea1.FI_01`.

## Receta N-edge

1. Un PostgreSQL compartido para catálogo e histórico.
2. Un proceso (o contenedor) por área, con `AUTOMATION_NODE_ID` y `AUTOMATION_AREA` únicos.
3. Journal SAF local por nodo: `./db/saf/<node_id>/journal.db`.
4. Clientes OPC UA con `owner_node` igual al `NODE_ID` del edge que los abre.
5. Comprobar `/api/health/system`: `ACQUISITION_READY=true`, `NODE_ID`, `NODE_AREA`, `SAF_QUEUE_DEPTH` y `DB_CONNECTIONS_COUNT` ≤ 4 idle por edge.

Ejemplo:

```ini
# Edge A
AUTOMATION_MULTI_EDGE_ENABLED=true
AUTOMATION_NODE_ID=edge-linea1
AUTOMATION_AREA=Linea1
AUTOMATION_SITE=Norte

# Edge B
AUTOMATION_MULTI_EDGE_ENABLED=true
AUTOMATION_NODE_ID=edge-linea2
AUTOMATION_AREA=Linea2
AUTOMATION_SITE=Norte
```

`application_name` de PostgreSQL queda `PyAutomationIO:<node_id>:<rol>` (máximo 63 caracteres).

## Rollback

1. Detener adquisición en todos los edges.
2. Arrancar una sola instancia con `AUTOMATION_MULTI_EDGE_ENABLED=false`.
3. No se infieren propietarios históricos: las columnas `area`/`owner_node` nulas permanecen nulas.
4. Restaurar el journal común `./db/saf/journal.db` si se usaba el layout legado.

## Evidencia CA-EDGE

| Criterio | Qué demuestra | Cómo verificar |
|---|---|---|
| CA-EDGE-1 | Tras reboot, el CVT no contiene tags de otra área | Suite `test_multi_edge_acceptance.TestAcceptanceCriteria.test_ca_edge_1_*` y reboot de un edge |
| CA-EDGE-2 | El edge no abre sesión OPC UA ajena | `test_ca_edge_2_*` y `test_opc_client_never_connects_for_foreign_owner` |
| CA-EDGE-3 | Samples trazables al nodo | `application_name` y `owner_node` en TagValue / `test_ca_edge_3_*` |
| CA-EDGE-4 | Caída de A: B sigue y no escribe tags de A | journals aislados + `test_ca_edge_4_*` |
| CA-EDGE-5 | Sin `NODE_ID`: no hay `read_all()` de tags/OPC | fail-closed en `connect_to_db` + `test_ca_edge_5_*` |
| CA-EDGE-6 | Homólogos cualificados coexisten | `Linea1.FI_01` y `Linea2.FI_01` + `test_ca_edge_6_*` |
| CA-EDGE-7 | Idle PG ≤ 4 por edge | `/api/health/system` → `DB_CONNECTIONS_EXPECTED_MAX` |
| CA-EDGE-8 | HMI local no lista puntos ajenos | API/Socket.IO acotados + `test_ca_edge_8_*` |

Integración 2-edge opt-in:

```bash
AUTOMATION_TWO_EDGE_IT=1 \
AUTOMATION_TWO_EDGE_EVIDENCE=/ruta/evidencia.txt \
python -m unittest automation.tests.test_multi_edge_acceptance.TestTwoEdgeLive
```

Soak 24 h (operación): dos edges, dos OPC UA, PostgreSQL compartido. No-Go ante escritura cruzada, sesión OPC ajena, crecimiento sostenido de `SAF_QUEUE_DEPTH`/`PENDING_ROWS` o contaminación del HMI/CVT.

Checklist operativo:

1. Arrancar Edge A (`Linea1`) y Edge B (`Linea2`) contra el mismo PostgreSQL.
2. Confirmar `/api/health/system`: `ACQUISITION_READY=true`, `DB_CONNECTIONS_COUNT` ≤ 4 idle, `SAF_QUEUE_DEPTH` estable.
3. Reboot de A: el CVT de A no lista `Linea2.*`; B sigue adquiriendo.
4. Caer OPC de A: A no abre el cliente de B; B no encola samples de A.
5. HMI de cada edge: listados de tags/alarmas/máquinas/clientes OPC solo del área local.
6. Tras 24 h, `PENDING_ROWS` no crece de forma sostenida y no hay writes cruzados en TagValue (`owner_node`).
