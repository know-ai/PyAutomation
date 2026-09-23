# ADR 001 — Servidor OPC UA embebido en asyncua

Fecha: 2026-09-23. Estado: aceptado.

El servidor embebido deja `opcua` 0.98.13, que no tiene parche para CVE-2022-25304 y concentra el tiempo de arranque en `add_nodes`. El reemplazo es `asyncua` 2.0.1 o posterior. Esa versión incluye el arreglo de la CVE a partir de 0.9.96.

Gunicorn usa gevent. asyncio y gevent no comparten loop. El servidor corre en un hilo de sistema obtenido con `gevent.monkey.get_original`, para que el parche de gevent no convierta ese hilo en un greenlet. El hilo de la máquina de estados solo mete comandos en una `queue.Queue` con `maxsize` 10000. El loop drena hasta 200 comandos y, si la cola está vacía, duerme 50 ms.

El cliente de campo (`automation/opcua/`, `managers/opcua_client.py`) también quedó en `asyncua`, en otro hilo (`opcua-asyncua-client`). `opcua==0.98.13` ya no está en `requirements.txt`. El paquete no instancia `opcua.Server` ni `opcua.Client`.

El NodeId, el árbol `PyAutomationIO/{site}/{area}/{Process,Alarms,Engines}` y el tope de properties no cambian. Security Policy no se activa. El símbolo `SecurityPolicyBasic256Sha256` queda importable para un sprint posterior.
