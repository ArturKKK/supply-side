"""Step 2 -- per-item volume via /market/priceoverview/ (no login, ever).

/market/pricehistory/ is deliberately NOT used: it is gated behind a logged-in
Steam session, and trading a real account's session for public price data is a
bad trade. That path is treated as closed, not as something to work around.
Price history, if wanted at all, comes from external aggregators as a supplement
(see external_history.py) -- never as the base of the product.

Priority: every case and capsule first, then stickers by current sell_listings.
Resumable: items that already have a volume reading today are skipped.
"""
import re
import sys
import time

import db
from steamclient import SteamClient, SteamClosed

OVERVIEW = "https://steamcommunity.com/market/priceoverview/"


def money(s):
    if not s:
        return None
    m = re.search(r"([\d.]+)", s.replace(",", ""))
    return float(m.group(1)) if m else None


def ensure_cols(c):
    for col, typ in (("median_usd", "REAL"), ("volume_24h", "INTEGER")):
        try:
            c.execute(f"ALTER TABLE snapshots ADD COLUMN {col} {typ}")
        except Exception:
            pass
    c.commit()


def targets(c, n_stickers=200):
    rows = list(c.execute("""
        SELECT i.name, i.class, COALESCE(s.sell_listings, 0)
        FROM items i
        LEFT JOIN (SELECT name, sell_listings,
                          ROW_NUMBER() OVER (PARTITION BY name ORDER BY ts DESC) rn
                   FROM snapshots) s ON s.name = i.name AND s.rn = 1"""))
    prio = sorted([r for r in rows if r[1] in ("case", "capsule")], key=lambda r: -r[2])
    stick = sorted([r for r in rows if r[1] == "sticker"], key=lambda r: -r[2])[:n_stickers]
    return [r[0] for r in prio + stick]


def run(cli, c, names, max_age_h=20):
    cutoff = int(time.time()) - max_age_h * 3600
    done = {n for (n,) in c.execute(
        "SELECT DISTINCT name FROM snapshots WHERE volume_24h IS NOT NULL AND ts>?",
        (cutoff,))}
    todo = [n for n in names if n not in done]
    print(f"[priceoverview] {len(todo)} to fetch, {len(done)} fresh already", flush=True)
    ok = fail = 0
    for i, name in enumerate(todo, 1):
        code, j = cli.get(OVERVIEW, params={"appid": 730, "market_hash_name": name,
                                            "currency": 1, "country": "US"},
                          expect_json=True)
        if code != 200 or not isinstance(j, dict) or not j.get("success"):
            fail += 1
            continue
        vol = j.get("volume")
        vol = int(str(vol).replace(",", "")) if vol else 0
        c.execute("""INSERT OR REPLACE INTO snapshots(name,ts,sell_listings,price_usd,
                       median_usd,volume_24h)
                     VALUES(?,?,(SELECT sell_listings FROM snapshots WHERE name=?
                                 ORDER BY ts DESC LIMIT 1),?,?,?)""",
                  (name, int(time.time()), name, money(j.get("lowest_price")),
                   money(j.get("median_price")), vol))
        ok += 1
        if ok % 25 == 0:
            c.commit()
            print(f"  {i}/{len(todo)} ok={ok} fail={fail} req={cli.n_req} "
                  f"429={cli.n_429}", flush=True)
    c.commit()
    print(f"[priceoverview] done ok={ok} fail={fail}", flush=True)


def main():
    n_st = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    c = db.connect()
    ensure_cols(c)
    names = targets(c, n_st)
    print(f"targets: {len(names)}", flush=True)
    cli = SteamClient(db.DB)
    try:
        run(cli, c, names)
    except SteamClosed as e:
        print(f"\nSTOPPED: {e}", flush=True)
        c.close()
        sys.exit(3)
    c.close()


if __name__ == "__main__":
    main()
