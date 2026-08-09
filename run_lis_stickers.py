"""Second LIS pass: every sticker in the target grid, including the ones the
Internet Archive had no history for.

That is the point. If a sticker has no archived Steam history *and* no LIS
listings, it is genuinely dead. If it has no archive history but a live LIS
order book, then the archive simply did not keep it -- which separates "we
cannot see it" from "it does not trade", and those are very different answers.
"""
import sys
import time

sys.path.insert(0, "/root/projects/supply-side")

import db      # noqa: E402
import lis     # noqa: E402

TARGETS = "/root/projects/supply-side/data/sticker_targets.txt"

if __name__ == "__main__":
    c = db.connect()
    names = [l.rstrip("\n") for l in open(TARGETS) if l.strip()]
    print(f"{len(names)} sticker targets, {time.strftime('%H:%M:%S')}", flush=True)
    lis.collect(c, names, "stickers-full-grid")
    c.close()
