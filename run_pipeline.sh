#!/bin/bash
# Quiet-window cooldown, then the collection chain.
# Steam's 429 appears to be extended by requests made while banned, so we stay
# silent for QUIET seconds between probes instead of polling every 2 min.
cd /root/projects/supply-side || exit 1
PY=./.venv/bin/python
QUIET=${QUIET:-900}

probe() {
    $PY - <<'EOF'
import sys, requests
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"})
try:
    r = s.get("https://steamcommunity.com/market/search/render/",
              params={"appid": 730, "norender": 1, "count": 1, "currency": 1}, timeout=30)
    print(r.status_code)
    sys.exit(0 if r.status_code == 200 else 1)
except Exception as e:
    print(type(e).__name__)
    sys.exit(1)
EOF
}

echo "=== quiet cooldown, ${QUIET}s between probes, $(date +%H:%M:%S) ==="
for i in $(seq 1 12); do
    sleep "$QUIET"
    code=$(probe)
    echo "  probe $i at $(date +%H:%M:%S) -> $code"
    [ "$code" = "200" ] && break
done
if [ "$code" != "200" ]; then
    echo "=== Steam still refusing after $((12 * QUIET / 60)) min of quiet probing. Stopping. ==="
    exit 3
fi

echo
echo "=== step1: containers $(date +%H:%M:%S) ==="
$PY -u step1_inventory.py containers || echo "step1 containers exit=$?"

echo
echo "=== status_load $(date +%H:%M:%S) ==="
$PY -u status_load.py | head -12

echo
echo "=== step1: stickers per capsule facet $(date +%H:%M:%S) ==="
$PY -u step1_inventory.py stickers || echo "step1 stickers exit=$?"

echo
echo "=== inventory complete $(date +%H:%M:%S) ==="
$PY -u db.py
