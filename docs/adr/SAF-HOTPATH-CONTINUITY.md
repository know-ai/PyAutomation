# ADR: Continuidad del hot path con Store-and-Forward

| Campo | Valor |
|---|---|
| Estado | Aceptado |
| Fecha | 2026-09-29 |
| Spec | SPEC-SAF-HOTPATH-CONTINUITY |
| Auditoría | [AUDIT_SAF_OUTAGE.md](../../audits/AUDIT_SAF_OUTAGE.md) |

## Contexto

Con PostgreSQL caído el journal SQLite conserva las filas, pero un solo `threading.Lock` mezclaba el `deque` del productor, el `fsync` del flusher, el `fetch_pending` del drenaje y el `VACUUM`. El ACK, además, hacía el `INSERT` remoto en el greenlet HTTP cuando la sonda veía el historiador vivo.

## Decisión

1. El anillo tiene su propio lock. El productor solo hace `deque.append` o un drop. No llama a `COMMIT`.
2. Una conexión escribe (`synchronous=FULL`). Otra, `mode=ro` y `query_only`, lee `fetch_pending` y la edad del pendiente. Sigue habiendo un solo writer: `SafEmergencyDrainer` y `SafJournalFlusher` serializan en ese lock. Dos writers sobre el mismo archivo no son WAL concurrente.
3. `VACUUM` en SQLite pide lock exclusivo. El tick no lo toma porque no entra al journal. Los lectores del journal sí pueden esperar un `VACUUM`, así que el compact solo corre en idle real.
4. El reloj de idle no lo reinician el tick ni el flush de tags. Lo reinician un write crítico, un ACK y el catch-up. Si no, con tags a 1 Hz el `VACUUM` no correría nunca.
5. `journal_then_remote` no escribe en PostgreSQL. Solo `ReplicationWorker` hace el `INSERT`. El fragmento del spec que aún escribía en línea “si la red está sana” rompe el p95 de 50 ms del ACK en régimen normal.
6. Al arrancar, toda fila `REPLICATING` vuelve a `PENDING`. No existe columna `replicating_since`. `attempts` no se incrementa.
7. Si el anillo está lleno solo de tags protegidos, el productor rechaza sin `fsync` y emite `SAF ring full`. No se puede a la vez no bloquear y no perder esa muestra.

## Consecuencias

`GET /api/health/ready` sigue en 200 `DEGRADED` durante la caída. No reiniciar el contenedor por ese probe. Un 503 de `POST /api/alarms/acknowledge` con `error_type=journal_error` es el journal local (disco o techo de filas), no PostgreSQL.

El soak de 24 h y el bench de 1 M filas quedan como campaña. El código no los certifica.
