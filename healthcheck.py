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


def _warn_db_mount_without_noatime():
    """Advisory only — never fails the orchestrator healthcheck."""
    data_dir = os.environ.get("AUTOMATION_DATA_DIR") or "/app/db"
    path = "/proc/self/mountinfo"
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return
    abs_target = os.path.abspath(data_dir)
    best = ""
    options = ""
    fstype = ""
    for line in text.splitlines():
        if " - " not in line:
            continue
        left, right = line.split(" - ", 1)
        left_parts = left.split()
        right_parts = right.split()
        if len(left_parts) < 6 or not right_parts:
            continue
        point, opts = left_parts[4], left_parts[5]
        if abs_target == point or abs_target.startswith(point.rstrip("/") + "/") or point == "/":
            if len(point) >= len(best):
                super_opts = right_parts[2] if len(right_parts) > 2 else ""
                best = point
                options = f"{opts},{super_opts}"
                fstype = right_parts[0]
    option_set = {part.strip() for part in options.split(",") if part.strip()}
    if best and "noatime" not in option_set:
        print(
            f"WARNING: data volume {abs_target} mounted without noatime ({best})",
            file=sys.stderr,
        )
    if best and fstype == "ext4" and not ({"data=ordered", "data=journal"} & option_set):
        print(
            f"WARNING: data volume {abs_target} ext4 without data=ordered ({best})",
            file=sys.stderr,
        )


def main():
    _warn_db_mount_without_noatime()
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
