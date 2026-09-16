# -*- coding: utf-8 -*-
"""Parse EXPLAIN ANALYZE JSON and score GATE-30 queries."""
from __future__ import annotations

import json
import re
import sys

THRESHOLDS = {
    "Q1": 5.0,
    "Q2": 5.0,
    "Q3": 10.0,
    "Q4": 5.0,
    "Q5": None,  # COUNT(*) lab anti-pattern; Seq Scan allowed
    "Q6": 10.0,
}


def _unmangle_psql(text: str) -> str:
    """psql aligned JSON uses '|' and '+' continuation markers."""
    lines = []
    for raw in text.splitlines():
        line = raw
        if "|" in line[:60] and '"Plan"' not in line[:20]:
            # drop leading '                    QUERY PLAN                     '
            if line.strip().startswith("QUERY PLAN") or set(line.strip()) <= {"-", "+", " "}:
                continue
            if line.strip() in ("(1 row)",):
                continue
        if line.startswith(" ") and "+" in line:
            pass
        # Typical: ' [                                                +'
        if line.rstrip().endswith("+"):
            line = line.rstrip()[:-1]
        if "|" in line:
            # ' [ ...' after alignment — keep after first |
            parts = line.split("|", 1)
            if len(parts) == 2 and parts[0].strip() == "":
                line = parts[1]
        lines.append(line.rstrip())
    return "\n".join(lines)


def extract_json_blocks(text: str) -> list:
    cleaned = _unmangle_psql(text)
    decoder = json.JSONDecoder()
    blocks = []
    idx = 0
    while True:
        start = cleaned.find("[", idx)
        if start < 0:
            break
        try:
            obj, end = decoder.raw_decode(cleaned, start)
        except json.JSONDecodeError:
            idx = start + 1
            continue
        if isinstance(obj, list) and obj and isinstance(obj[0], dict) and "Plan" in obj[0]:
            blocks.append(obj)
            idx = end
        else:
            idx = start + 1
    return blocks


def has_seq_scan(plan: dict) -> bool:
    if plan.get("Node Type") == "Seq Scan":
        return True
    for child in plan.get("Plans", []) or []:
        if has_seq_scan(child):
            return True
    return False


def get_index_names(plan: dict) -> list[str]:
    indexes = []
    if "Index Name" in plan:
        indexes.append(plan["Index Name"])
    for child in plan.get("Plans", []) or []:
        indexes.extend(get_index_names(child))
    return indexes


def analyze(blocks: list) -> dict:
    results = {}
    for i, block in enumerate(blocks, start=1):
        key = f"Q{i}"
        plan = block[0]["Plan"]
        exec_ms = float(block[0].get("Execution Time") or 0.0)
        seq = has_seq_scan(plan)
        verdict = "PASS"
        if key == "Q5":
            verdict = "N/A (COUNT(*) anti-pattern)"
        elif seq:
            verdict = "FAIL (Seq Scan)"
        elif THRESHOLDS.get(key) is not None and exec_ms > THRESHOLDS[key]:
            verdict = f"FAIL ({exec_ms:.2f}ms > {THRESHOLDS[key]}ms)"
        results[key] = {
            "seq_scan": seq,
            "indexes": get_index_names(plan),
            "exec_ms": exec_ms,
            "threshold_ms": THRESHOLDS.get(key),
            "verdict": verdict,
            "node": plan.get("Node Type"),
        }
    return results


if __name__ == "__main__":
    path = sys.argv[1]
    text = open(path, encoding="utf-8").read()
    blocks = extract_json_blocks(text)
    results = analyze(blocks)
    print(f"Encontrados {len(blocks)} bloques EXPLAIN")
    print()
    print(f"{'Query':<6} {'Seq Scan':<10} {'Exec (ms)':<12} {'Índices':<42} {'Veredicto'}")
    print("=" * 100)
    failed = 0
    for q, row in results.items():
        idx_str = ",".join(row["indexes"])[:40] or "-"
        print(
            f"{q:<6} {str(row['seq_scan']):<10} {row['exec_ms']:<12.2f} {idx_str:<42} {row['verdict']}"
        )
        if row["verdict"].startswith("FAIL"):
            failed += 1
    sys.exit(1 if failed else 0)
