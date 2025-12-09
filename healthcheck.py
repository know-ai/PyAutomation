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
    
    # Try HTTP
    http_url = f"http://127.0.0.1:{port}/api/healthcheck/"
    if check_url(http_url):
        sys.exit(0)

    # Try HTTPS (ignoring self-signed certs for localhost healthcheck if needed)
    https_url = f"https://127.0.0.1:{port}/api/healthcheck/"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    if check_url(https_url, context=ctx):
        sys.exit(0)

    sys.exit(1)

if __name__ == "__main__":
    main()

