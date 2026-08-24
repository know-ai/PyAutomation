"""
Búsqueda i18n inversa para filtros de texto en alarmas y eventos.

Los mensajes persistidos en BD están en inglés; la HMI los muestra en español.
``expand_search_term`` amplía un término escrito en español con las claves
inglesas cuya traducción contiene ese término.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).resolve().parent / "data" / "i18n_map.json"


@lru_cache(maxsize=1)
def get_translation_map() -> dict[str, str]:
    """Mapa inglés → español cargado una vez desde ``automation/data/i18n_map.json``."""
    try:
        raw = _DATA_FILE.read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("No se pudo cargar i18n_map.json: %s", exc)
        return {}
    if not isinstance(parsed, dict):
        logger.warning("i18n_map.json debe ser un objeto JSON")
        return {}
    out: dict[str, str] = {}
    for key, value in parsed.items():
        if isinstance(key, str) and isinstance(value, str) and key and value:
            out[key] = value
    return out


def expand_search_term(q: str, translation_map: dict[str, str] | None = None) -> list[str]:
    """
    Dado un término de búsqueda, devuelve términos para consultar en BD (inglés).

    Siempre incluye el término original y añade claves inglesas cuya traducción
    al español contiene ``q`` (case-insensitive).
    """
    q_norm = str(q or "").strip()
    if not q_norm:
        return []
    q_lower = q_norm.lower()
    terms: list[str] = [q_norm]
    seen = {q_lower}
    mapping = translation_map if translation_map is not None else get_translation_map()
    for en, es in mapping.items():
        if q_lower not in es.lower():
            continue
        en_lower = en.lower()
        if en_lower in seen:
            continue
        seen.add(en_lower)
        terms.append(en)
    return terms


def icontains_any(field, terms: Iterable[str]):
    """Condición Peewee OR: ``field`` contiene alguno de los términos (iLIKE)."""
    from functools import reduce
    from operator import or_

    from peewee import fn

    normalized = [str(t).strip().lower() for t in terms if str(t).strip()]
    if not normalized:
        return None
    conditions = [fn.LOWER(field).contains(term) for term in normalized]
    return reduce(or_, conditions)
