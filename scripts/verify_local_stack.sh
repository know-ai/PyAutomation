#!/bin/bash
set -euo pipefail

echo "=== Verificando stack local ==="

echo "--- Containers ---"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" \
    | grep -E "app_db|idetect_db|redis|opcua" || {
    echo "FAIL: falta algún container (app_db/redis/opcua)"
    exit 1
}

echo "--- PostgreSQL (app_db :32800, database app_db) ---"
docker exec app_db psql -U postgres -d app_db \
    -c "SELECT 'PG OK' AS status, version();" || {
    echo "FAIL: PostgreSQL no responde"
    exit 1
}

echo "--- Redis ---"
docker exec compose-redis-session-1 redis-cli ping | grep -q PONG || {
    echo "FAIL: Redis no responde"
    exit 1
}
echo "Redis OK"

echo "--- OPC UA ---"
cd "$(dirname "$0")/.."
./venv/bin/python - <<'EOF'
from opcua import Client
c = Client("opc.tcp://127.0.0.1:4840")
c.connect()
try:
    root = c.get_root_node()
    name = root.get_browse_name()
    fi = c.get_node("ns=2;i=2")
    print(f"OPC UA OK: {name} FI_01={fi.get_value()}")
finally:
    c.disconnect()
EOF

echo "=== Stack verificado ==="
