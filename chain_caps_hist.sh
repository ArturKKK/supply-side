#!/bin/bash
cd /root/projects/supply-side || exit 1
while pgrep -f "external_histor[y].py" >/dev/null; do sleep 20; done
echo "=== capsule history from archive $(date +%H:%M:%S) ==="
mapfile -t N < data/archive_capsules.txt
./.venv/bin/python -u external_history.py "${N[@]}"
echo "=== capsule history done $(date +%H:%M:%S) ==="
