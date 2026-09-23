# Glosario OPC UA — acceso y multi-hop

- **AccessLevel**: máscara de 7 bits de OPC UA Part 3. `CurrentRead` 0x01, `CurrentWrite` 0x02, `HistoryRead` 0x04, `HistoryWrite` 0x08, `SemanticChange` 0x10, `StatusWrite` 0x20, `TimestampWrite` 0x40. En v1 `UserAccessLevel` es igual a `AccessLevel`. `AccessRestrictions` queda en 0.
- **Read / Write / ReadWrite**: etiquetas de las máscaras 1, 2 y 3. No son un catálogo aparte.
- **source**: origen de un valor en el CVT. `internal` es el default de los motores. `external` es un write del SCADA o de `POST /api/tags/write_value`. `field` es DAS o DAQ. `rollback` devuelve el valor previo y se vuelve a publicar.
- **transaction_id**: identificador de un write externo. Viaja en la descripción de los eventos de acceso.
- **command window**: 5 s después de un write aceptado por el PLC. Una muestra de campo con el mismo valor no cuenta como oscilación. Un valor distinto del PLC pisa el CVT.
- **depth**: saltos de propagación. Por encima de 3 el router rechaza el reenvío.
