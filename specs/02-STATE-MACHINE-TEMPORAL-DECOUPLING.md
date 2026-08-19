# Documento 02: Desacoplamiento temporal del muestreo y la ejecución

> Especificación PyAutomationIO (**v1.0**, 2026-08-18).  
> **Estado:** implementado en código (modo legado por defecto).  
> **Auditoría de contraste:** [`audits/AUDIT_STATE_MACHINES.md`](../audits/AUDIT_STATE_MACHINES.md).

<a id="objetivo"></a>

Contrato: tres relojes independientes — **adquisición** (`scan_time`) → **muestreo** (`sample_interval`) → **ejecución** (`execution_interval`) — con la regla de oro `execution_interval >= sample_interval >= scan_time`. Cierra SM-H1 cuando el operador activa muestreo personalizado.

`sample_interval IS NULL` = **modo legado** (iDetectFugas sin cambios, CA-SM-04).

Implementación: `automation/state_machine_timing.py`, `SampleSchedThread` en `automation/workers/state_machine.py`, columnas `execution_interval` / `sample_interval` / `sample_override`, validador en `PUT /machines/<name>/attributes`.

Criterios: CA-SM-01 … CA-SM-05 en `automation/tests/test_state_machine_timing.py`. Soak 24 h de CA-SM-05 en planta (CPU &lt; 0.5 % a 1 kHz) queda como certificación operativa.
