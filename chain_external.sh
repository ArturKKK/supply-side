#!/bin/bash
cd /root/projects/supply-side || exit 1
while pgrep -f "external_histor[y].py" >/dev/null; do sleep 20; done
echo "=== retry pass (CDX failures) + corrected names $(date +%H:%M:%S) ==="
./.venv/bin/python -u external_history.py \
  "CS:GO Weapon Case" "Chroma Case" "CS20 Case" "Gamma Case" "Prisma Case" \
  "Kilowatt Case" "Revolution Case" "Dreams & Nightmares Case" \
  "Fever Case" "Recoil Case" "Fracture Case" "Snakebite Case"
echo "=== retry pass done $(date +%H:%M:%S) ==="
