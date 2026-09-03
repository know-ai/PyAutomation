# -*- coding: utf-8 -*-
"""Session-based protection for Swagger /api/docs (Integrator + system only)."""
from __future__ import annotations

import os
import re
import time
from datetime import timedelta

from flask import Blueprint, redirect, render_template_string, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from ..utils.system_user import is_system_username

DOCS_PROTECTED_PREFIXES = (
    "/api/docs",
    "/api/swagger",
    "/api/swagger.json",
    "/api/swaggerui",
)

DOCS_RATE_LIMIT = os.environ.get("DOCS_RATE_LIMIT", "5 per minute")
DOCS_RATE_LIMIT_BLOCK = os.environ.get("DOCS_RATE_LIMIT_BLOCK", "5 minutes")
DOCS_SESSION_MINUTES = int(os.environ.get("DOCS_SESSION_MINUTES", "30") or "30")

login_manager = LoginManager()
login_manager.login_view = "docs_auth.login_docs"

limiter = Limiter(key_func=get_remote_address, default_limits=[], on_breach=lambda _limit: _on_rate_limit_breach(_limit))

docs_auth_bp = Blueprint("docs_auth", __name__)

_blocked_until: dict[str, float] = {}


class DocsUser(UserMixin):
    def __init__(self, username: str):
        self.id = username
        self.username = username


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    normalized = "/" + str(path).lstrip("/")
    if len(normalized) > 1:
        normalized = normalized.rstrip("/")
    return normalized or "/"


def is_docs_path(path: str) -> bool:
    exact = _normalize_path(path)
    for prefix in DOCS_PROTECTED_PREFIXES:
        base = _normalize_path(prefix)
        if exact == base or exact.startswith(f"{base}/"):
            return True
    return False


def _parse_block_seconds(value: str) -> float:
    text = str(value or "5 minutes").strip().lower()
    match = re.match(r"^(\d+(?:\.\d+)?)\s*(second|seconds|minute|minutes|hour|hours)$", text)
    if not match:
        return 300.0
    amount = float(match.group(1))
    unit = match.group(2)
    if unit.startswith("second"):
        return amount
    if unit.startswith("minute"):
        return amount * 60.0
    return amount * 3600.0


def _docs_system_password() -> str:
    return (
        os.environ.get("DOCS_SYSTEM_PASSWORD")
        or os.environ.get("AUTOMATION_SUPERUSER_PASSWORD")
        or "super_ultra_secret_password"
    )


def authenticate_docs_user(username: str, password: str) -> DocsUser | None:
    name = str(username or "").strip()
    if not name or password is None:
        return None
    if is_system_username(name):
        if password == _docs_system_password():
            return DocsUser("system")
        return None
    from ..modules.users.users import Auth, Users as CVTUsers

    users = CVTUsers()
    if not users.check_username(name):
        return None
    user = users.get_by_username(username=name)
    if user is None:
        return None
    role_name = str(getattr(getattr(user, "role", None), "name", "") or "").strip().lower()
    if role_name != "integrator":
        return None
    if not Auth().verify_credentials(user=user, password=password):
        return None
    return DocsUser(user.username)


@login_manager.user_loader
def load_docs_user(user_id: str) -> DocsUser | None:
    username = str(user_id or "").strip()
    if not username:
        return None
    if is_system_username(username):
        return DocsUser("system")
    from ..modules.users.users import Users as CVTUsers

    user = CVTUsers().get_by_username(username=username)
    if user is None:
        return None
    role_name = str(getattr(getattr(user, "role", None), "name", "") or "").strip().lower()
    if role_name != "integrator":
        return None
    return DocsUser(user.username)


def _is_ip_blocked(ip: str) -> bool:
    until = _blocked_until.get(ip)
    if until is None:
        return False
    if time.time() >= until:
        _blocked_until.pop(ip, None)
        return False
    return True


def _block_ip(ip: str) -> None:
    _blocked_until[ip] = time.time() + _parse_block_seconds(DOCS_RATE_LIMIT_BLOCK)


LOGIN_TEMPLATE = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Acceso a documentación API</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #f4f6f8; margin: 0; min-height: 100vh; display: grid; place-items: center; }
    .card { background: #fff; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,.08); width: min(420px, 92vw); padding: 2rem; }
    h1 { font-size: 1.25rem; margin: 0 0 .5rem; }
    p { color: #5f6b7a; font-size: .95rem; }
    label { display: block; font-size: .85rem; margin: 1rem 0 .35rem; color: #334155; }
    input { width: 100%; box-sizing: border-box; padding: .65rem .75rem; border: 1px solid #cbd5e1; border-radius: 8px; }
    button { margin-top: 1.25rem; width: 100%; padding: .75rem; border: 0; border-radius: 8px; background: #0d6efd; color: #fff; font-weight: 600; cursor: pointer; }
    .error { background: #fde8e8; color: #b42318; border-radius: 8px; padding: .75rem; margin-top: 1rem; font-size: .9rem; }
    .hint { margin-top: 1rem; font-size: .8rem; color: #64748b; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Documentación Swagger</h1>
    <p>Acceso restringido a usuarios <strong>system</strong> o rol <strong>Integrator</strong>.</p>
    <form method="post" action="{{ action_url }}">
      <label for="username">Usuario</label>
      <input id="username" name="username" type="text" autocomplete="username" required>
      <label for="password">Contraseña</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required>
      <button type="submit">Entrar</button>
    </form>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <div class="hint">Tras iniciar sesión podrá cerrarla en <code>/logout-docs</code>.</div>
  </div>
</body>
</html>
"""


@docs_auth_bp.route("/login-docs", methods=["GET"])
def login_docs_get():
    if current_user.is_authenticated:
        target = request.args.get("next") or "/api/docs"
        return redirect(target)
    return render_template_string(
        LOGIN_TEMPLATE,
        action_url=url_for("docs_auth.login_docs_post"),
        error=None,
    )


@docs_auth_bp.route("/login-docs", methods=["POST"])
@limiter.limit(DOCS_RATE_LIMIT, methods=["POST"])
def login_docs_post():
    ip = get_remote_address()
    if _is_ip_blocked(ip):
        return (
            render_template_string(
                LOGIN_TEMPLATE,
                action_url=url_for("docs_auth.login_docs_post"),
                error="Demasiados intentos. Intente más tarde.",
            ),
            429,
        )
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    user = authenticate_docs_user(username, password)
    if user is None:
        return (
            render_template_string(
                LOGIN_TEMPLATE,
                action_url=url_for("docs_auth.login_docs_post"),
                error="Credenciales inválidas o usuario sin permisos.",
            ),
            401,
        )
    login_user(user, remember=True, duration=timedelta(minutes=DOCS_SESSION_MINUTES))
    target = request.args.get("next") or request.form.get("next") or "/api/docs"
    if not is_docs_path(target):
        target = "/api/docs"
    return redirect(target)


@docs_auth_bp.route("/logout-docs")
@login_required
def logout_docs():
    logout_user()
    return redirect(url_for("docs_auth.login_docs_get"))


def _on_rate_limit_breach(_request_limit):
    _block_ip(get_remote_address())
    return (
        render_template_string(
            LOGIN_TEMPLATE,
            action_url=url_for("docs_auth.login_docs_post"),
            error="Demasiados intentos. Intente más tarde.",
        ),
        429,
    )


def protect_docs_request():
    """Redirect unauthenticated clients away from Swagger UI/spec paths."""
    if not is_docs_path(request.path):
        return None
    if current_user.is_authenticated:
        return None
    return redirect(url_for("docs_auth.login_docs_get", next=request.path))


def init_app(app) -> None:
    secret = (
        os.environ.get("DOCS_SECRET_KEY")
        or app.config.get("AUTOMATION_APP_SECRET_KEY")
        or "pyautomation-docs-session"
    )
    app.config["SECRET_KEY"] = secret
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    if os.environ.get("DOCS_SESSION_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "on"}:
        app.config["SESSION_COOKIE_SECURE"] = True
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=DOCS_SESSION_MINUTES)

    login_manager.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(docs_auth_bp)
    app.before_request(protect_docs_request)
