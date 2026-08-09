"""Load per-source drop-pool claims into status_sources, one row per (item, source).

Nothing is merged here. resolve() only reports how many distinct verdicts an item
has; when sources disagree the item is marked `disputed` and the detail column
carries every verdict verbatim, so the disagreement stays visible downstream.
"""
import json
import time

import db

CLAIMS = "/root/projects/supply-side/data/status_claims.json"

BUCKETS = [("active", "active_drop"),
           ("armory_exchange", "armory_exchange"),
           ("purchase_only", "purchase_only"),
           ("rare_pool_partial", "rare_pool"),
           ("discontinued", "discontinued")]


def load(c):
    claims = json.load(open(CLAIMS))
    ts = int(time.time())
    c.execute("DELETE FROM status_sources")
    unmatched = []
    known = {n for (n,) in c.execute("SELECT name FROM items")}
    for src in claims["sources"]:
        sid = src["id"]
        note = f"page_updated={src.get('page_updated_claim')}; url={src['url']}"
        for key, status in BUCKETS:
            for name in src.get(key, []):
                if known and name not in known:
                    unmatched.append((sid, name))
                c.execute(
                    "INSERT OR REPLACE INTO status_sources(name,source,status,note,ts)"
                    " VALUES(?,?,?,?,?)", (name, sid, status, note, ts))
    c.commit()
    return unmatched


def resolve(c):
    """-> {name: (status, detail)}. Disagreement is preserved, never voted away."""
    out = {}
    rows = c.execute("SELECT name,source,status FROM status_sources ORDER BY name,source")
    per = {}
    for name, source, status in rows:
        per.setdefault(name, []).append((source, status))
    for name, lst in per.items():
        verdicts = sorted({s for _, s in lst})
        detail = "; ".join(f"{src}={st}" for src, st in lst)
        if len(verdicts) == 1:
            out[name] = (verdicts[0], f"{len(lst)} source(s) agree: {detail}")
        else:
            out[name] = ("disputed", f"sources disagree: {detail}")
    return out


if __name__ == "__main__":
    c = db.connect()
    unmatched = load(c)
    res = resolve(c)
    from collections import Counter
    print("status_sources rows:",
          c.execute("SELECT COUNT(*) FROM status_sources").fetchone()[0])
    print("items with >=1 claim:", len(res))
    for k, v in Counter(s for s, _ in res.values()).most_common():
        print(f"  {k:16s} {v}")
    if unmatched:
        print(f"\nnames claimed by a source but NOT found on the market ({len(unmatched)}):")
        for sid, n in unmatched:
            print(f"  {sid:26s} {n}")
    print("\ndisputed items:")
    for n, (s, d) in sorted(res.items()):
        if s == "disputed":
            print(f"  {n:34s} {d}")
    c.close()
