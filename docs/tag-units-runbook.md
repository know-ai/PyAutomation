# Runbook: unidades de tags (v1)

Contrato: [specs/12-TAG-UNITS-CONTRACT.md](../specs/12-TAG-UNITS-CONTRACT.md).  
Este deploy **no cambia** símbolos ya persistidos. Solo congela la unidad en muestras SAF **nuevas** y deja de pisar filas en bootstrap.

## Antes del wheel 2.10

1. Backup de PostgreSQL/MySQL (tablas `tags`, `units`, `tagvalue`).
2. Backup de `./db/catalog.db` en cada edge.
3. Drenar SAF: `GET /api/health/system` → `SAF_QUEUE_DEPTH` / `PENDING_ROWS` en 0 (o aceptar que muestras **viejas** en journal no traen `unit` y caerán al fallback **CA-UNIT-11**).
4. Anotar `PI_*` / `FI_*` actuales (`unit`, `display_unit`) por si hay que comparar después.

## Deploy

1. Instalar el wheel PyAutomationIO reconstruido desde `github/PyAutomation`.
2. Arrancar la app. `ensure_schema` añade columnas nullable `unit_source` y `unit_locked_at` (no reescribe unidades).
3. En logs de boot debe aparecer `Unit migrations dry-run: no pending…` o un warning de cambios **pendientes no aplicados**.
4. Verificar `GET /api/health/system`:
   - `SAF_SAMPLES_WITHOUT_UNIT` (sube al drenar journal legado; no es fallo del deploy).
   - `UNITS_MISMATCH_COUNT` (conversión SI imposible).

## `unit_source` NULL

Filas anteriores a 2.10 quedan en `NULL`. Las migraciones las tratan como **`engine`**. Un `PUT /api/tags` posterior marca `operator` y **nunca** entra en migraciones automáticas.

## Dry-run / apply (opt-in)

```http
POST /api/admin/unit-migrations/dry-run
POST /api/admin/unit-migrations/apply
{"confirm": true}
```

Roles: dry-run admin/supervisor/integrator; apply admin/integrator.  
Alternativa de planta: `AUTOMATION_UNIT_MIGRATIONS_APPLY=1` + el mismo POST (o scripts internos). **Nunca** se aplica solo por arrancar.

Registro inicial:

- `PI_*` `bar` → `Pa`
- `FI_*` `kg/s` → `kg/sec`

Evento de auditoría: `Unit migrated: <name>`.

## Rollback

- El journal SAF con claves extra (`unit`, `unit_source`, `display_unit_at_sample`) es válido en mapper 2.9: **ignora claves desconocidas**.
- Las columnas nuevas son nullable: un wheel anterior sigue leyendo `tags`.
- No hace falta vaciar `tagvalue`. Las muestras nuevas llevan el símbolo congelado; las antiguas no se reetiquetan.

## Operación

- No cambiar `unit` de `PI_*` / `FI_*` a mano salvo corrección consciente (queda `operator`).
- En v1, `display_unit` **sí** es la unidad del CVT y del historiador, no un adorno HMI.
- Alias aceptados en API: `kg/s`→`kg/sec`, `m3/s`/`m³/s`→`m3/sec`, `°K`→`K`, `barg`→`bar`.
