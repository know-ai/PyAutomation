# Servidor OPC UA embebido

Un solo plano de publicación: `CanonicalPublisher`.

Árbol: `Objects/PyAutomationIO/{Site}/{Area}/{Process,Alarms,Engines}`.

NodeId: `ns=<idx>;s=<t|a|e>:<nombre>`. `MANUFACTURER` y `SEGMENT` son carpetas de navegación. El nombre calificado ya incluye el segmento.

Endpoint: `opc.tcp://{AUTOMATION_OPCUA_SERVER_HOST}:{AUTOMATION_OPCUA_SERVER_PORT}/OPCUAServer/` (por defecto `0.0.0.0:53530`).

El arranque encola las entidades existentes. El tick las materializa en FIFO.
