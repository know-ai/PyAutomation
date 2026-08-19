# Despliegue NTP — disciplina del SO y monitor PyAutomation

PyAutomationIO usa una arquitectura de **dos capas**:

1. **Capa 1 — SO del edge** (`chrony` en Linux, `w32time` en Windows): disciplina el reloj del sistema.
2. **Capa 2 — Monitor PyAutomation** (`NtpMonitorWorker`): verifica periódicamente el desfase contra servidores NTP de planta vía **SNTP/UDP 123** (IPv4 e IPv6).

El monitor **no mueve el reloj** del sistema. Detecta deriva, saltos bruscos y fallos de conectividad.

## Requisitos de red

| Requisito | Detalle |
|---|---|
| Protocolo | SNTP (RFC 4330) sobre **UDP puerto 123** |
| Direcciones | IPv4, IPv6 o hostname (resolución DNS dual-stack) |
| Credenciales | **No** en modo estándar |
| Autenticación | Claves simétricas NTP y NTS **no soportadas** en v2.0 — el monitor reportará `auth_required_detected` |
| Firewall edge | **Salida UDP 123** hacia servidores NTP de planta |
| Firewall servidor | **Entrada UDP 123** desde VLAN OT |

Configure los **mismos servidores** en chrony/w32time del host y en **HMI → Configuración → Sincronización NTP**.

## Servidor NTP en Linux (chrony)

```ini
# /etc/chrony/chrony.conf
server 192.168.10.5 iburst
server 192.168.10.6 iburst
allow 192.168.0.0/16
makestep 1.0 3
rtcsync
```

```bash
sudo systemctl enable --now chrony
chronyc tracking
chronyc sources -v
```

## Servidor NTP en Windows Server (w32time)

1. Activar servicio **Windows Time** (`w32time`).
2. Configurar como servidor NTP (registro `NtpServer`, `AnnounceFlags` — ver documentación Microsoft).
3. Firewall: regla **entrante UDP 123** desde la VLAN OT.
4. Probar desde un edge:

```powershell
w32tm /config /manualpeerlist:"192.168.10.5,0x8 192.168.10.6,0x8" /syncfromflags:manual /update
net stop w32time && net start w32time
w32tm /query /status
```

> En dominios AD, valide que el servidor responda a edges Linux fuera del dominio. Si no, use un servidor NTP Linux dedicado en OT.

## Edge Linux (cliente + monitor)

```bash
# chrony apunta a planta
grep ^server /etc/chrony/chrony.conf

# Verificación manual SNTP
ntpdate -q 192.168.10.5   # si ntpdate está instalado

# API PyAutomation
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/system/clock | jq .
curl -s -X POST -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/system/clock/check
```

## Edge Windows (cliente + monitor)

Configure `w32time` contra los mismos servidores. PyAutomation ejecuta el monitor SNTP en el proceso Python con los mismos requisitos de red UDP 123.

## Configuración HMI

| Campo | Recomendación planta |
|---|---|
| Servidores NTP | `192.168.10.5, 192.168.10.6` (IP preferida en OT) |
| Intervalo | 3600 s (1 h) |
| Umbral advertencia | 50 ms |
| Umbral alarma | 1000 ms |
| Fail-closed | Política de planta (opcional) |

**Tooltip en HMI:** compatible con Linux (chrony/ntpd) y Windows Server (w32time) sin credenciales.

## Troubleshooting

| Síntoma | Causa probable | Acción |
|---|---|---|
| `last_error: timed out` | Firewall, servidor caído, VLAN incorrecta | Verificar UDP 123; ping no basta (NTP es UDP) |
| `could not resolve NTP host` | DNS OT | Usar IP directa o corregir DNS |
| `Authentication required` | Servidor exige clave simétrica/NTS | Usar servidor sin auth en VLAN OT o esperar P3 |
| Offset alto pero probe OK | chrony/w32time mal configurado en host | Corregir Capa 1; el monitor solo verifica |
| `jump_detected: true` | Salto manual o `makestep` agresivo | Revisar chrony; evento en bitácora |
| IPv6 falla, IPv4 OK | Normal en dual-stack | El monitor prueba ambas automáticamente |

## Variables de entorno (bootstrap opcional)

Solo si la clave no está persistida en `app_config.json`:

- `AUTOMATION_NTP_SERVERS`
- `AUTOMATION_NTP_CHECK_INTERVAL_S`
- `AUTOMATION_NTP_WARN_OFFSET_MS`
- `AUTOMATION_NTP_ALARM_OFFSET_MS`
- `AUTOMATION_NTP_STEP_THRESHOLD_MS` (default 2000)
- `AUTOMATION_NTP_FAIL_CLOSED`
- `AUTOMATION_NTP_ENABLED`

Prioridad: **HMI / app_config.json > env > defaults**.

## Criterios de aceptación

Ver `automation/tests/test_ntp_monitor.py` (CA-NTP-01 … CA-NTP-18) y soak multi-edge CA-NTP-06/07 (Fase C).
