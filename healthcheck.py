import urllib.request
import os
import sys
import ssl

def check_url(url, context=None):
    try:
        with urllib.request.urlopen(url, context=context, timeout=15) as response:
            return response.status == 200
    except Exception:
        return False

def main():
    port = os.environ.get("PORT", "8050")
    
    # Prefer explicit API health endpoint if available
    # New REST health resource: /api/health/ping
    http_health_url = f"http://127.0.0.1:{port}/api/health/ping"
    if check_url(http_health_url):
        sys.exit(0)

    # Fallback: check application root (many deployments expose a 200 here)
    http_root_url = f"http://127.0.0.1:{port}/"
    if check_url(http_root_url):
        sys.exit(0)

    # Try HTTPS variants (ignoring self-signed certs for localhost healthcheck if needed)
    https_health_url = f"https://127.0.0.1:{port}/api/health/ping"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    if check_url(https_health_url, context=ctx):
        sys.exit(0)

    https_root_url = f"https://127.0.0.1:{port}/"
    if check_url(https_root_url, context=ctx):
        sys.exit(0)

    # None of the URLs responded with HTTP 200
    sys.exit(1)

if __name__ == "__main__":
    main()

