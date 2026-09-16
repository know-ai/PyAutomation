# ISA18-2-PARTITION-PLAN — GATE-33

| Campo | Valor |
|---|---|
| **Fecha** | 2026-09-16 |
| **SHA** | `7ee3df9527c5141e8bc963b856cd569f95aa8a1e` |
| **Tabla** | `public.alarmsummary` (lab PG 17, `app_db`) |
| **Tamaño medido** | total **295 MB** · data **159 MB** · indexes **135 MB** · 1 000 010 filas |

## Output crudo (`scripts/check_partition_readiness.sql`)

```
=== PK ===
 attname |  type
---------+--------
 id      | bigint
(1 row)

=== CONSTRAINTS ===
      conname      | contype
-------------------+---------
 alarmsummary_pkey | p
(1 row)

=== SIZE ===
 total  |  data  | indexes
--------+--------+---------
 295 MB | 159 MB | 135 MB

=== FK ONTO alarmsummary ===
(0 rows)
```

## Criterios

| # | Criterio | Resultado |
|---|---|---|
| CA-F10-1 | PK usa BIGINT | **PASS** (`id bigint`) |
| CA-F10-2 | PK o índice **único** incluye `event_time` | **FAIL** — PK solo `id`. Índices `(event_time)` y `(alarm_id, event_time)` **no únicos** |
| CA-F10-3 | Sin FK que impida particionar | **PASS** (0 FKs hacia `alarmsummary`) |
| CA-F10-4 | Plan documentado | **PASS** (este archivo) |

GATE-33: **PARCIAL**. Listo para particionar en el sentido de FKs y tipo de PK; **no** listo para `PARTITION BY RANGE (event_time)` nativo sin cambiar la PK.

## Plan (no ejecutado en esta spec)

PostgreSQL exige que toda unique/PK de una tabla particionada **incluya la clave de partición**.

1. Ventana de mantenimiento. Snapshot `pg_dump` de `alarmsummary`.
2. Crear tabla nueva:

```sql
CREATE TABLE alarmsummary_p (
    LIKE alarmsummary INCLUDING DEFAULTS INCLUDING IDENTITY
) PARTITION BY RANGE (event_time);

ALTER TABLE alarmsummary_p
    ADD PRIMARY KEY (id, event_time);

-- Particiones mensuales (retención P2 ≥ 1 año → 12+1 rolling)
CREATE TABLE alarmsummary_p_2026_09 PARTITION OF alarmsummary_p
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
```

3. Recrear índices no únicos por partición:
   - `(alarm_id, event_time DESC)`
   - `(to_state, event_time DESC)`
   - `(event_time DESC)` (a menudo cubierto por la PK)
4. `INSERT INTO alarmsummary_p SELECT * FROM alarmsummary;` + `VALIDATE`.
5. Swap de nombre en transacción corta + actualizar secuencia.
6. `sample_uuid` permanece UNIQUE **global** solo si se añade a la PK o se mueve a índice no único (el producto ya permite UUID en texto; unicidad de negocio se valida en tests, no en PK).

**No se migra ahora:** CA-F10-2 es un gap de esquema lab/producto. P2 retención/archivo usará este plan.

Waiver W-PG-06 firmado 2026-09-16 SHA `7ee3df9527c5141e8bc963b856cd569f95aa8a1e`: PK sin `event_time`; evidencia `\d alarmsummary` arriba.
