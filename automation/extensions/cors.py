"""
CORS para la API Flask / Socket.IO.

Configuración por entorno:

- ``AUTOMATION_CORS_ORIGINS``:
  - ``*`` (default): cualquier origen.
  - Lista separada por comas, p.ej.
    ``http://192.168.1.10:3000,http://localhost:5173``
- ``AUTOMATION_CORS_CREDENTIALS``:
  - ``true`` solo tiene efecto con orígenes explícitos (no con ``*``).
    Necesario si el cliente envía cookies / ``credentials: 'include'``.
"""
from __future__ import annotations

import os

from flask import make_response, request
from flask_cors import CORS

from ..singleton import Singleton


_CORS_METHODS = "GET, HEAD, POST, OPTIONS, PUT, PATCH, DELETE"
_CORS_MAX_AGE = "86400"


def _parse_cors_origins() -> str | list[str]:
    raw = (os.environ.get("AUTOMATION_CORS_ORIGINS") or "*").strip()
    if not raw or raw == "*":
        return "*"
    origins = [part.strip() for part in raw.split(",") if part.strip()]
    return origins if origins else "*"


def _cors_credentials_enabled(origins: str | list[str]) -> bool:
    if origins == "*":
        return False
    flag = (os.environ.get("AUTOMATION_CORS_CREDENTIALS") or "false").strip().lower()
    return flag in ("1", "true", "yes", "on")


class Cors(Singleton):

    def __init__(self):
        self.app = None
        self.origins: str | list[str] = "*"
        self.supports_credentials = False

    def init_app(self, app):
        r"""
        CORS configurable.

        Con ``AUTOMATION_CORS_ORIGINS=*`` (default) se permite cualquier origen.
        ``supports_credentials`` solo aplica con orígenes explícitos (requisito del navegador).
        El handler OPTIONS evita que flask-restx / auth respondan 401/405 al preflight.
        """
        self.origins = _parse_cors_origins()
        self.supports_credentials = _cors_credentials_enabled(self.origins)
        use_wildcard = self.origins == "*"

        cors_kwargs = {
            "resources": {r"/*": {"origins": self.origins}},
            "origins": self.origins,
            "methods": ["GET", "HEAD", "POST", "OPTIONS", "PUT", "PATCH", "DELETE"],
            "allow_headers": "*",
            "expose_headers": "*",
            "supports_credentials": self.supports_credentials,
            "send_wildcard": use_wildcard,
            "automatic_options": True,
            "max_age": int(_CORS_MAX_AGE),
        }
        self.app = CORS(app, **cors_kwargs)

        @app.before_request
        def _cors_preflight():
            if request.method != "OPTIONS":
                return None

            response = make_response("", 204)
            origin = request.headers.get("Origin")
            if use_wildcard:
                response.headers["Access-Control-Allow-Origin"] = "*"
            elif origin and isinstance(self.origins, list) and origin in self.origins:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Vary"] = "Origin"
                if self.supports_credentials:
                    response.headers["Access-Control-Allow-Credentials"] = "true"
            elif origin:
                # Origen no listado: responder sin ACAO (el navegador bloqueará).
                pass
            else:
                response.headers["Access-Control-Allow-Origin"] = (
                    self.origins[0] if isinstance(self.origins, list) and self.origins else "*"
                )

            response.headers["Access-Control-Allow-Methods"] = _CORS_METHODS
            response.headers["Access-Control-Allow-Headers"] = (
                request.headers.get("Access-Control-Request-Headers") or "*"
            )
            response.headers["Access-Control-Max-Age"] = _CORS_MAX_AGE
            return response

        return app
