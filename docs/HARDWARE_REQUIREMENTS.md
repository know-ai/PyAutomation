# Requisitos de almacenamiento para borde industrial

| Campo | Valor |
|---|---|
| **Producto** | PyAutomationIO + iDetectFugas |
| **Alcance** | SSD, filesystem, planificador I/O, SMART, power-loss |
| **Objetivo** | Vida útil ≥ 5 años en operación 24/7/365 |
| **Fecha** | 2026-08-28 |

El journal SAF (`./db/saf/<node_id>/journal.db`, `synchronous=FULL` + `os.fsync` post-COMMIT) y `catalog.db` viven en el volumen de datos. Ese volumen **debe** ser un SSD de grado industrial, no un eMMC de consumo ni un HDD.

## SSD industrial

| Requisito | Mínimo | Notas |
|---|---|---|
| Capacidad | **256 GB** dedicados a `/app/db` (o `AUTOMATION_DATA_DIR`) | Separar del SO y de logs Docker |
| Resistencia | **≥ 0.5 DWPD** durante 5 años (≈ 230 TBW en 256 GB) | Preferible ≥ 1 DWPD |
| Tecnología | 3D TLC o superior, con wear leveling y over-provisioning de fábrica | Evitar QLC de consumo |
| Temperatura | **0 °C a 70 °C** en operación continua | Verificar derating del fabricante |
| Factor de forma | M.2 2280 o 2.5" SATA según chasis | Preferir NVMe industrial |
| Ejemplos | Innodisk 3IE2 / 3ME3, Transcend Industrial, Swissbit, o equivalente IEC 60721 | No es una lista cerrada |

Over-provisioning: dejar ≥ 10 % del disco sin particionar si el firmware no reserva OP.

## Protección ante corte de energía (power-loss)

El software no puede inventar un capacitor. Sin hardware power-fail-safe, `synchronous=FULL` + `fsync` reducen la ventana de corrupción pero **no** la cierran al 100 % si el SSD pierde writes en vuelo.

| Capa | Requisito | Por qué |
|---|---|---|
| UPS del edge | Autonomía ≥ 5 min + apagado ordenado (SIGTERM → Docker stop) | Evita SIGKILL por brown-out |
| SSD con PLP | Capacitores o firmware power-loss-protection (industrial, no consumer DRAM-less sin PLP) | Completa los flushes NAND |
| `synchronous=FULL` | Ya en journal SAF | SQLite fsync del WAL en cada COMMIT |
| `os.fsync` extra | FD de solo lectura sobre `journal.db` tras COMMIT | Cinturón sobre el kernel writeback |
| ext4 `data=ordered` | En el host (el bind Docker hereda) | Metadata no adelanta a datos |
| Ensayo | T-01 Apocalypse (`SIGKILL` + replay exact-once) | [docs/CHAOS_TESTING.md](./CHAOS_TESTING.md) |

No usar QLC de consumo ni RAID software sobre USB. Preferir NVMe industrial con PLP explícito en la hoja de datos.

## Sistema de archivos

Tipo: **ext4** o **XFS**.

Opciones de montaje recomendadas para el volumen de datos:

```fstab
# /etc/fstab — volumen dedicado a /var/lib/idetectfugas/db (bind a /app/db)
UUID=…  /var/lib/idetectfugas/db  ext4  defaults,noatime,commit=30,data=ordered  0  2
```

| Opción | Por qué |
|---|---|
| `noatime` | Evita escrituras de atime en cada lectura del journal/WAL |
| `commit=30` | Agrupa metadata; 30 s es un compromiso durabilidad/IOPS en borde |
| `data=ordered` | Metadata no se escribe antes de los datos (ext4) |

Docker: el bind `./data/db:/app/db` **hereda** las opciones del filesystem del host. Configure `noatime` en el host, no dentro del contenedor.

La aplicación **advierte** (no tumba el healthcheck) si el volumen de datos no tiene `noatime` o si ext4 carece de `data=ordered`. Snapshot: `HOST_DISK_NOATIME`, `HOST_DISK_DATA_ORDERED`, `HOST_DISK_FSTYPE`, `HOST_DISK_IO_SCHEDULER` en `GET /api/health/node`.

## Planificador I/O

```bash
# NVMe (baja latencia, el host ya ordena)
echo none > /sys/block/nvme0n1/queue/scheduler

# SATA SSD
echo mq-deadline > /sys/block/sda/queue/scheduler
```

Persistir con udev o `GRUB_CMDLINE_LINUX` (`elevator=` está obsoleto en kernels modernos; use `none` / `mq-deadline` vía sysfs o `IOScheduler=` en systemd).

## Monitoreo SMART

En el host (o con `smartctl` bind-mounted al contenedor):

```bash
AUTOMATION_SSD_DEVICE=/dev/nvme0n1
AUTOMATION_SSD_WEAR_WARN=80
AUTOMATION_SSD_TEMP_WARN=65
```

El sampler lee `smartctl -A -j` cada 60 s y publica `HOST_SSD_WEAR_PERCENT`, `HOST_SSD_TEMP_C`. La alarma ISA-18.2 es **`ALM.PERF.SSD`** cuando wear o temperatura superan el umbral.

En imagen distroless **no** hay `smartctl`. Opciones:

1. Privileged sidecar que escribe un JSON que el sampler aún no consume — use `smartctl` en el host y monte el dispositivo.
2. Bind-mount del binario + `/dev` (requiere `--privileged` o cap `SYS_RAWIO`; documentar el riesgo).
3. Exporter node-exporter `smartctl` en el host y correlacionar en el SIEM.

Sin `AUTOMATION_SSD_DEVICE` o sin `smartctl`, las métricas quedan `null` y **no** se dispara `ALM.PERF.SSD` (evita falsos positivos).

## Checklist de puesta en marcha

- [ ] SSD industrial con TBW ≥ 0.5 DWPD / 5 años **y** PLP o UPS ≥ 5 min
- [ ] Volumen dedicado, no el disco del SO
- [ ] ext4/xfs con `noatime,commit=30,data=ordered`
- [ ] Scheduler `none` (NVMe) o `mq-deadline` (SATA)
- [ ] `AUTOMATION_SSD_DEVICE` definido y SMART visible en `/performance`
- [ ] Alarma `ALM.PERF.SSD` reconocida en un ensayo de umbral de laboratorio
