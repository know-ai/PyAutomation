#!/usr/bin/env bash
# Pre-flight: list DOWN Docker bridges that steal 172.21/172.22 (HMI/OPC routes).
# Does NOT run `docker network rm` or `ip addr del`. Operator decides in plant.
set -euo pipefail

echo "=== Docker networks ==="
if command -v docker >/dev/null 2>&1; then
  docker network ls || true
else
  echo "docker CLI not available"
fi

echo
echo "=== Bridge links (ip -br link) ==="
ip -br link show type bridge 2>/dev/null || ip -br link | grep -E 'br-|docker' || true

echo
echo "=== Addresses on DOWN / orphan bridges (172.21, 172.22) ==="
found=0
while read -r iface state rest; do
  [ -n "${iface:-}" ] || continue
  case "$iface" in
    br-*|docker0) ;;
    *) continue ;;
  esac
  addrs=$(ip -4 addr show dev "$iface" 2>/dev/null | awk '/inet / {print $2}' || true)
  echo "$iface state=${state} addrs=${addrs:-<none>}"
  if echo "$addrs" | grep -Eq '172\.2[12]\.'; then
    found=1
    echo "  WARNING: $iface holds 172.21/172.22 — can black-hole HMI/OPC. Do not auto-rm in plant."
  fi
  if [ "${state}" = "DOWN" ]; then
    echo "  NOTE: $iface is DOWN (orphan candidate). Inspect with: docker network ls / ip addr show $iface"
  fi
done < <(ip -br link 2>/dev/null || true)

echo
if [ "$found" -eq 1 ]; then
  echo "Duplicate subnet detected. Manual recovery (lab only): ip addr del <cidr> dev <bridge>"
  echo "Never run docker network rm automatically on a plant host."
  exit 2
fi
echo "No 172.21/172.22 addresses found on docker bridges."
exit 0
