"""Runner: feed the selected sticker targets to external_history without a
304-argument command line (which made the wrapper shell fragile)."""
import sys

sys.path.insert(0, "/root/projects/supply-side")

TARGETS = "/root/projects/supply-side/data/sticker_targets.txt"
names = [l.rstrip("\n") for l in open(TARGETS) if l.strip()]
sys.argv = ["external_history.py"] + names

import external_history  # noqa: E402

external_history.main()
