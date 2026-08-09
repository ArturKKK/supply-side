#!/bin/bash
cd /root/projects/supply-side || exit 1
while pgrep -f "external_histor[y].py" >/dev/null; do sleep 20; done
echo "=== control group C: major capsules (never in any drop pool) $(date +%H:%M:%S) ==="
./.venv/bin/python -u external_history.py \
  "Cologne 2016 Legends (Holo/Foil)" "Atlanta 2017 Legends (Holo/Foil)" \
  "Boston 2018 Legends (Holo/Foil)" "Katowice 2019 Legends (Holo/Foil)" \
  "Berlin 2019 Legends (Holo/Foil)" "Stockholm 2021 Legends Sticker Capsule" \
  "Antwerp 2022 Legends Sticker Capsule" "Rio 2022 Legends Sticker Capsule" \
  "Paris 2023 Legends Sticker Capsule" "Copenhagen 2024 Legends Sticker Capsule" \
  "Community Sticker Capsule 1" "Sticker Capsule 2"
echo "=== control group C done $(date +%H:%M:%S) ==="
