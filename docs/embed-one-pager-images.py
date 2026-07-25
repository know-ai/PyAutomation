#!/usr/bin/env python3
"""Embed local images into automation-one-pager.html for offline distribution.

Usage (from docs/):
    python3 embed-one-pager-images.py

Reads automation-one-pager.src.html (relative image paths) and writes
automation-one-pager.html with base64 data URIs — single file, no external assets.
"""

from __future__ import annotations

import base64
import mimetypes
import re
import sys
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent
SRC = DOCS_DIR / "automation-one-pager.src.html"
OUT = DOCS_DIR / "automation-one-pager.html"

SRC_PATTERN = re.compile(
    r'src=(["\'])(\./[^"\']+\.(?:png|jpe?g|webp|gif|svg))\1',
    re.IGNORECASE,
)


def embed_images(html: str) -> tuple[str, int]:
    count = 0

    def replacer(match: re.Match[str]) -> str:
        nonlocal count
        quote, rel_path = match.group(1), match.group(2)
        file_path = (DOCS_DIR / rel_path[2:]).resolve()
        if not file_path.is_file():
            print(f"ERROR: missing {file_path}", file=sys.stderr)
            return match.group(0)
        mime, _ = mimetypes.guess_type(str(file_path))
        if not mime:
            mime = "application/octet-stream"
        data = base64.b64encode(file_path.read_bytes()).decode("ascii")
        count += 1
        kb = file_path.stat().st_size // 1024
        print(f"  embedded {rel_path} ({kb} KB)")
        return f"src={quote}data:{mime};base64,{data}{quote}"

    return SRC_PATTERN.sub(replacer, html), count


def main() -> int:
    if not SRC.is_file():
        print(f"ERROR: source not found: {SRC}", file=sys.stderr)
        return 1

    html = SRC.read_text(encoding="utf-8")
    embedded, count = embed_images(html)
    if count == 0:
        print("ERROR: no images embedded — check src paths", file=sys.stderr)
        return 1

    dist_comment = (
        "<!-- Distribución: archivo autocontenido — capturas embebidas en base64. "
        "Editar automation-one-pager.src.html y ejecutar embed-one-pager-images.py -->\n"
    )
    if embedded.startswith("<!DOCTYPE html>\n<!--"):
        embedded = "<!DOCTYPE html>\n" + dist_comment + embedded.split("\n", 2)[-1]
    elif embedded.startswith("<!DOCTYPE html>\n"):
        embedded = "<!DOCTYPE html>\n" + dist_comment + embedded[len("<!DOCTYPE html>\n") :]

    OUT.write_text(embedded, encoding="utf-8")
    mb = OUT.stat().st_size / 1024 / 1024
    print(f"\nWrote {OUT.name} ({count} images, {mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
