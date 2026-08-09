#!/bin/bash
cd /root/projects/supply-side || exit 1
while pgrep -f "li[s].py collect" >/dev/null; do sleep 20; done
echo "=== LIS pass 2: full sticker grid $(date +%H:%M:%S) ==="
./.venv/bin/python -u run_lis_stickers.py
echo "=== LIS pass 2 done $(date +%H:%M:%S) ==="
