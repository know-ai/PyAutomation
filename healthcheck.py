import urllib.request
import os
import sys
import ssl


def _cert_paths():
    cert_env = (os.environ.get("AUTOMATION_CERT_FILE") or os.environ.get("CERT_FILE") or "").strip()
    key_env = (os.environ.get("AUTOMATION_KEY_FILE") or os.environ.get("KEY_FILE") or "").strip()

    def resolve(raw: str) -> str:
        if not raw:
            return ""
        if raw.startswith("/"):
            return raw
        return os.path.join("/app", "ssl", raw)

    return resolve(cert_env), resolve(key_env)


def _ssl_enabled() -> bool:
    cert, key = _cert_paths()
    return bool(cert and key and os.path.isfile(cert) and os.path.isfile(key))


def check_url(url, context=None):
    try:
        with urllib.request.urlopen(url, context=context, timeout=15) as response:
            return response.status == 200
    except Exception:
        return False


def main():
    port = os.environ.get("AUTOMATION_PORT") or os.environ.get("PORT", "8050")
    use_ssl = _ssl_enabled()
    scheme = "https" if use_ssl else "http"
    health_url = f"{scheme}://127.0.0.1:{port}/api/health/ping"
    root_url = f"{scheme}://127.0.0.1:{port}/"
    ctx = None
    if use_ssl:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    if check_url(health_url, context=ctx):
        sys.exit(0)
    if check_url(root_url, context=ctx):
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
