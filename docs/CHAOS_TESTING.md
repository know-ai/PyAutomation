# Pruebas de caos — PyAutomationIO / iDetectFugas

| Campo | Valor |
|---|---|
| **Objetivo** | Validar RTO/RPO y recuperación automática ante fallos de red, disco, nodo y energía |
| **Audiencia** | Laboratorio OT, no CI de cada commit |
| **Evidencia** | [audits/CHAOS_LAST_RUN.md](../audits/CHAOS_LAST_RUN.md) |
| **Fecha** | 2026-08-28 |

Estas pruebas **no se simulan como “planta 24 h” en GitLab CI**. Los unitarios cubren el mecanismo; la campaña de laboratorio rellena el artefacto.

## Objetivos de recuperación (contrato)

| Métrica | Objetivo de laboratorio | Cómo se mide |
|---|---|---|
| **RPO** (pérdida de muestras) | **0** muestras ACK en historiador duplicadas o perdidas tras SIGKILL del proceso | TagValue unique `(tag, timestamp)` + journal PENDING replay |
| **RTO** caída de historiador | Cola SAF acotada; drenaje a 0 cuando PG vuelve | `SAF_QUEUE_DEPTH` T0 → pico → 0 |
| **RTO** reinicio de contenedor | HMI y ping listos en **≤ `_restart_eta_s`** (~30 s overlay, no 10 s; LGBM en background) | Reloj de overlay HMI / `GET /api/health/ping` |
| **RTO** edge down (par) | Detección `ALM.PERF.NODE_DOWN` en **≤ `AUTOMATION_PEER_STALE_S` + debounce** (~90–105 s) | HMI `/performance` del edge vivo |
| **RPO** corte de red OPC | 0 samples del área ajena; samples locales en journal | `owner_node` + journal |

**No hay RTO de “Edge B asume I/O de A”.** El diseño es partición single-writer: la línea de A deja de adquirir hasta que A vuelve. Eso es intencional (anti split-brain).

## Campañas

### C-01 Energía / SIGKILL (T-01 Apocalypse)

```bash
cd github/PyAutomation
SAF_SOAK_SECONDS=60 SAF_SOAK_TAGS=100 SAF_SOAK_HZ=50 \
  python -m unittest automation.tests.test_store_and_forward.TestT01Apocalypse
```

Pasa si el journal sobrevive y el replay es exact-once. Complemento: UPS + SSD PLP en [HARDWARE_REQUIREMENTS.md](./HARDWARE_REQUIREMENTS.md).

### C-02 Historiador caído

1. Dos edges en lab, PG compartido.
2. `docker stop` del Postgres 15–30 min (o 4 h en soak disco).
3. Confirmar `SAF_QUEUE_DEPTH` crece, circuit breaker open, **0** pérdida en journal.
4. Arrancar PG; cola → 0; sin duplicados TagValue.

### C-03 Red / disco lleno

- Unitario: `test_disk_full_error_*`, circuit breaker en `test_store_and_forward.py`.
- Lab: `fallocate` hasta el tope del volumen de `data/db` y verificar `JournalDiskFullError` / `ALM.PERF` disco, sin WAL corrupto.

### C-04 Nodo par caído

1. Arrancar Linea1 y Linea2.
2. `docker stop` Linea1.
3. En Linea2, esperar `HOST_PEER_DOWN=1` y `ALM.PERF.NODE_DOWN`.
4. Confirmar que Linea2 **no** escribe tags `Linea1.*`.
5. Arrancar Linea1; alarma se limpia; journal de Linea1 drena.

### C-05 Reloj

1. Desfasar el host > 1 s (solo lab) o mock NTP.
2. Confirmar `ALM.PERF.NTP` (~100 ms) y `ALM.NTP.OutOfSync` (1 s).
3. Confirmar que SAF **no** replica (`last_error` clock offset) y PENDING permanece.

## CI (opcional, corto)

```bash
python -m unittest \
  automation.tests.test_store_and_forward \
  automation.tests.test_mission_critical \
  automation.tests.test_disk_durability \
  automation.tests.test_catalog_sqlite
```

No habilitar soak 24 h en el pipeline de merge.

## Tras cada campaña de lab

Copiar resultados a [audits/CHAOS_LAST_RUN.md](../audits/CHAOS_LAST_RUN.md). Enlazar desde [AUDIT_MISSION_CRITICAL.md](../audits/AUDIT_MISSION_CRITICAL.md).
