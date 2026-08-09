"""Off-Steam liquidity via the LIS-SKINS public API.

Why this exists. Steam's 30-day volume is not a measure of how sellable an item
is -- it is a measure of how sellable it is *on Steam*. Steam charges ~13% and
pays into a wallet that cannot be cashed out, so cheap items (a $0.42 capsule,
where the fee is pennies and the balance gets spent on games) trade there while
expensive ones (holo and autograph stickers) trade on cash marketplaces. That
makes Steam volume a biased liquidity proxy in a specific direction: it
overstates the cheap class and understates the expensive one. Any conclusion of
the form "stickers rise but cannot be sold" has to survive this check before it
is worth anything.

This is a standalone client. It reads the API key out of /opt/vulpes/.env and
copies nothing else: vulpes' own client, service and databases are untouched.
"""
import json
import os
import re
import sqlite3
import statistics as st
import sys
import time

import requests

import db

ENV = "/opt/vulpes/.env"
BASE = "https://api.lis-skins.com/v1"
PACE = 2.0                      # seconds between requests, deliberately slow
BACKOFF = [30, 60, 120, 300]


def api_key(path=ENV):
    if not os.path.exists(path):
        return None
    for line in open(path):
        m = re.match(r"\s*LIS_API_KEY\s*=\s*(.+?)\s*$", line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return None


class Lis:
    def __init__(self, key):
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {key}",
                               "Accept": "application/json"})
        self._last = 0.0
        self.n_req = self.n_429 = 0

    def _wait(self):
        d = PACE - (time.time() - self._last)
        if d > 0:
            time.sleep(d)
        self._last = time.time()

    def get(self, path, params):
        for i, w in enumerate([0] + BACKOFF):
            if w:
                print(f"    LIS backoff {w}s", flush=True)
                time.sleep(w)
            self._wait()
            try:
                r = self.s.get(BASE + path, params=params, timeout=30)
            except requests.RequestException as e:
                print(f"    LIS net {type(e).__name__}", flush=True)
                continue
            self.n_req += 1
            if r.status_code == 200:
                try:
                    return r.json()
                except json.JSONDecodeError:
                    return None
            if r.status_code == 429:
                self.n_429 += 1
                continue
            if r.status_code in (500, 502, 503, 504):
                continue
            print(f"    LIS HTTP {r.status_code} {r.text[:120]}", flush=True)
            return None
        return None

    def search_name(self, name, max_pages=6):
        """All listings for one exact market name. -> (items, censored).
        censored=True means we stopped at the page cap, so the count is a floor."""
        out, cursor = [], None
        for _ in range(max_pages):
            p = {"game": "csgo", "names[]": name, "sort_by": "newest"}
            if cursor:
                p["cursor"] = cursor
            body = self.get("/market/search", p)
            if not body:
                break
            data = body.get("data") or []
            out.extend(data)
            cursor = (body.get("meta") or {}).get("next_cursor")
            if not cursor or not data:
                return out, False
        return out, True


def ensure(c):
    c.execute("""CREATE TABLE IF NOT EXISTS offsteam (
        name TEXT, source TEXT, ts INTEGER,
        listings INTEGER, min_price REAL, median_price REAL, censored INTEGER,
        PRIMARY KEY (name, source, ts))""")
    c.commit()


def price_of(item):
    for k in ("price", "current_price", "price_usd"):
        v = item.get(k)
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                pass
    return None


def collect(c, names, label=""):
    key = api_key()
    if not key:
        print("no LIS_API_KEY found -- cannot measure off-Steam liquidity")
        return False
    cli = Lis(key)
    ensure(c)
    done = {n for (n,) in c.execute(
        "SELECT DISTINCT name FROM offsteam WHERE source='lis' AND ts>?",
        (int(time.time()) - 86400,))}
    todo = [n for n in names if n not in done]
    print(f"[lis] {label} {len(todo)} names to query ({len(done)} fresh)", flush=True)
    ts = int(time.time())
    found = 0
    for i, n in enumerate(todo, 1):
        items, censored = cli.search_name(n)
        prices = [p for p in (price_of(x) for x in items) if p]
        c.execute("INSERT OR REPLACE INTO offsteam"
                  "(name,source,ts,listings,min_price,median_price,censored)"
                  " VALUES(?,?,?,?,?,?,?)",
                  (n, "lis", ts, len(items),
                   min(prices) if prices else None,
                   st.median(prices) if prices else None, int(censored)))
        if items:
            found += 1
        if i % 10 == 0:
            c.commit()
            print(f"  {i}/{len(todo)} | with listings: {found} | "
                  f"req={cli.n_req} 429={cli.n_429}", flush=True)
    c.commit()
    print(f"[lis] {label} done: {found}/{len(todo)} names have listings on LIS",
          flush=True)
    return True


if __name__ == "__main__":
    c = db.connect()
    what = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if what == "probe":
        key = api_key()
        print("api key found:", bool(key))
        if not key:
            sys.exit(1)
        cli = Lis(key)
        for n in ("Sticker | Astralis (Holo) | Krakow 2017",
                  "Antwerp 2022 Challengers Sticker Capsule",
                  "Sticker | AdreN (Gold) | Krakow 2017",
                  "AK-47 | Redline (Field-Tested)"):
            items, censored = cli.search_name(n)
            pr = [p for p in (price_of(x) for x in items) if p]
            print(f"  {n[:46]:46s} listings={len(items):4d} "
                  f"min={min(pr) if pr else '-'} med={st.median(pr) if pr else '-'}")
            if items:
                print(f"     sample keys: {sorted(items[0].keys())[:12]}")
    else:
        names = [n for (n,) in c.execute(
            "SELECT name FROM metrics WHERE class IN ('sticker','capsule') ORDER BY name")]
        collect(c, names, "sticker+capsule")
    c.close()
