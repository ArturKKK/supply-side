#!/bin/bash
cd /root/projects/supply-side || exit 1
while pgrep -f "external_histor[y].py" >/dev/null; do sleep 20; done
echo "=== remaining cases from source-claimed names $(date +%H:%M:%S) ==="
mapfile -t N < data/todo_cases.txt
./.venv/bin/python -u external_history.py "${N[@]}"
echo "=== remaining cases done $(date +%H:%M:%S) ==="
