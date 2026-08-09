"""Step 1 -- inventory of the three fixed-supply classes.

Containers come from Steam's own Type facet (tag_CSGO_Type_WeaponCase = "Container").
Stickers are walked per Sticker-Collection facet, so every sticker carries the
source capsule Steam itself assigns it -- no name guessing, no invented mapping.

Resumable: progress lives in run_meta, re-running continues where it stopped.
"""
import json
import re
import sys
import time

import db
from steamclient import SteamClient, SteamClosed, search_page

FILTERS = "/root/projects/supply-side/data/appfilters_730.json"


def load_facets():
    with open(FILTERS) as f:
        return json.load(f)["facets"]


def classify(name, steam_type):
    """Name/type-derived class. Everything unclear stays container_other."""
    n = name.lower()
    if "capsule" in n:
        return "capsule", "name contains 'capsule'"
    if "souvenir package" in n:
        return "souvenir", "name contains 'souvenir package'"
    if re.search(r"\bcase\b", n) and "key" not in n:
        return "case", "name matches /\\bcase\\b/ without 'key'"
    if "sticker |" in n or (steam_type or "").lower() == "sticker":
        return "sticker", "steam type/prefix = sticker"
    for kw, lbl in (("pins capsule", "capsule"), ("graffiti", "container_other"),
                    ("patch pack", "capsule"), ("music kit box", "container_other"),
                    ("autograph", "capsule"), ("challengers", "capsule"),
                    ("legends", "capsule"), ("champions", "capsule"),
                    ("contenders", "capsule")):
        if kw in n:
            return lbl, f"name contains '{kw}'"
    return "container_other", "container, no case/capsule keyword"


def get_meta(c, k, default=None):
    r = c.execute("SELECT v FROM run_meta WHERE k=?", (k,)).fetchone()
    return r[0] if r else default


def set_meta(c, k, v):
    c.execute("INSERT OR REPLACE INTO run_meta(k,v) VALUES(?,?)", (k, str(v)))
    c.commit()


def store(c, results, source_capsule=None, source_tag=None, force_class=None):
    ts = int(time.time())
    n_new = 0
    for r in results:
        name = r.get("hash_name") or r.get("name")
        if not name:
            continue
        ad = r.get("asset_description") or {}
        stype = ad.get("type")
        cls, basis = classify(name, stype)
        if force_class:
            cls, basis = force_class, "sticker-collection facet membership"
        cur = c.execute("SELECT source_capsule FROM items WHERE name=?", (name,)).fetchone()
        if cur is None:
            c.execute("""INSERT INTO items(name,class,class_basis,source_capsule,source_tag,
                                           steam_type,first_seen) VALUES(?,?,?,?,?,?,?)""",
                      (name, cls, basis, source_capsule, source_tag, stype, ts))
            n_new += 1
        elif source_capsule and not cur[0]:
            c.execute("UPDATE items SET source_capsule=?,source_tag=? WHERE name=?",
                      (source_capsule, source_tag, name))
        price = r.get("sell_price")
        c.execute("INSERT OR REPLACE INTO snapshots(name,ts,sell_listings,price_usd) "
                  "VALUES(?,?,?,?)",
                  (name, ts, r.get("sell_listings"),
                   (price / 100.0) if isinstance(price, int) else None))
    c.commit()
    return n_new


def walk(cli, c, label, extra, progress_key, force_class=None,
         source_capsule=None, source_tag=None, hard_cap=40000):
    """Paginate one facet query to exhaustion, resuming from run_meta."""
    start = int(get_meta(c, progress_key, 0))
    if start < 0:
        return 0
    total = None
    got = 0
    while True:
        j = search_page(cli, start, 100, extra=extra)
        if j is None:
            print(f"  {label}: page start={start} failed, will resume later", flush=True)
            return got
        total = j.get("total_count", 0)
        res = j.get("results") or []
        if not res:
            break
        got += store(c, res, source_capsule, source_tag, force_class)
        start += len(res)
        set_meta(c, progress_key, start)
        if start % 1000 == 0 or start >= total:
            print(f"  {label}: {start}/{total}  (+{got} new)", flush=True)
        if start >= total or start >= hard_cap:
            break
    set_meta(c, progress_key, -1)
    print(f"  {label}: DONE {start}/{total}, {got} new items", flush=True)
    return got


def main():
    c = db.connect()
    cli = SteamClient(db.DB)
    facets = load_facets()
    which = sys.argv[1] if len(sys.argv) > 1 else "all"

    try:
        if which in ("all", "containers"):
            print("[containers] Type=Container (tag_CSGO_Type_WeaponCase)", flush=True)
            walk(cli, c, "containers",
                 {"category_730_Type[]": "tag_CSGO_Type_WeaponCase"},
                 "inv:containers")

        if which in ("all", "stickers"):
            caps = facets["730_StickerCapsule"]["tags"]
            print(f"[stickers] walking {len(caps)} sticker-collection facets", flush=True)
            for i, (tag, meta) in enumerate(caps.items(), 1):
                loc = meta.get("localized_name") or tag
                key = f"inv:cap:{tag}"
                if get_meta(c, key) == "-1":
                    continue
                print(f"  [{i}/{len(caps)}] {loc}", flush=True)
                walk(cli, c, loc,
                     {"category_730_Type[]": "tag_CSGO_Tool_Sticker",
                      "category_730_StickerCapsule[]": "tag_" + tag},
                     key, force_class="sticker",
                     source_capsule=loc, source_tag=tag)
    except SteamClosed as e:
        print(f"\nSTOPPED: Steam refused sustained requests -- {e}", flush=True)
        set_meta(c, "last_stop", f"SteamClosed @ {int(time.time())}: {e}")
        c.close()
        sys.exit(3)

    n = c.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    print(f"\nitems in db: {n}   requests: {cli.n_req}   429s: {cli.n_429}", flush=True)
    c.close()


if __name__ == "__main__":
    main()
