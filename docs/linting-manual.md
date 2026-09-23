# Revisión manual del lint OPC UA

Estas dos reglas no tienen checker estático. Se revisan en el pull request.

## AP-6 — Orden de publicación

El address space de un tag se crea en un solo `materialize_*`. No se publica la variable en un tick y las properties en otro. Si un cambio parte el alta, el revisor lo rechaza.

## AP-10 — Contrato de complejidad en el docstring

Todo método nuevo de publisher, tracker, watchdog o regla de lint declara su Big O en el docstring. Un método de tick que pase de O(B + K) no entra.

## Exención

Una línea puede llevar `# noqa: AP-X` con la regla concreta. La exención vale solo para esa línea. AP-8 del presupuesto de tick está exento porque el evento de sistema se escribe solo cuando el tick ya superó los 100 ms.
"""
