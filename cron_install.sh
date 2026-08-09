#!/bin/bash
# Daily supply snapshot at 03:17 local. Nothing else on this box is touched.
LINE='17 3 * * * cd /root/projects/supply-side && ./.venv/bin/python -u snapshot.py >> /root/projects/supply-side/logs_snapshot.txt 2>&1'
( crontab -l 2>/dev/null | grep -v 'supply-side/snapshot.py' ; echo "$LINE" ) | crontab -
echo "installed:"; crontab -l | grep supply-side
