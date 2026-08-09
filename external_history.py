"""External price/volume history via the Internet Archive.

Steam's own listing pages stopped carrying `var line1=[...]` when the market was
rewritten as an SSR app. Captures taken before that rewrite still carry the full
daily series (price + units sold, from the item's first day on the market up to
the capture date). The Wayback Machine is a public archive of public pages; this
is a supplement, not the base of the product, and it is explicitly not Steam.

Per item: walk captures newest -> oldest until one still contains line1, parse
it, store with source='wayback' plus the capture date so staleness is visible.
"""
import gzip
import json
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict

import db

UA = {"User-Agent": "supply-side/1.0 (one-off research; contact via repo)"}
CDX = ("http://web.archive.org/cdx/search/cdx?url={u}&output=json"
       "&from={frm}&to={to}&filter=statuscode:200&collapse=timestamp:6&limit=60")
MONTH = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
PAUSE = 3.0


def _get(url, timeout=120, tries=4):
    last = None
    for i in range(tries):
        time.sleep(PAUSE * (1 + i * 3))          # archive.org rate-limits too
        try:
            r = urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=timeout)
            b = r.read()
            if b[:2] == b"\x1f\x8b":
                b = gzip.decompress(b)
            return b.decode("utf-8", "ignore")
        except Exception as e:
            last = e
            print(f"      archive {type(e).__name__} (try {i + 1}/{tries})", flush=True)
    raise last


def captures(name, frm="20251001", to="20260810"):
    u = urllib.parse.quote(
        f"steamcommunity.com/market/listings/730/{name}", safe="")
    try:
        rows = json.loads(_get(CDX.format(u=u, frm=frm, to=to), timeout=90))
    except Exception as e:
        print(f"    cdx fail {type(e).__name__}", flush=True)
        return []
    return [r[1] for r in rows[1:]] if len(rows) > 1 else []


def parse_line1(html):
    m = re.search(r"var line1=(\[.*?\]);", html)
    if not m:
        return None, None
    nid = re.search(r"Market_LoadOrderSpread\(\s*(\d+)", html)
    daily = defaultdict(lambda: [0.0, 0])
    for p in json.loads(m.group(1)):
        mon, dd, yy = p[0].split(" ")[:3]
        day = f"{yy}-{MONTH[mon]:02d}-{int(dd):02d}"
        v = int(p[2])
        daily[day][0] += float(p[1]) * v
        daily[day][1] += v
    return daily, (nid.group(1) if nid else None)


def fetch_item(c, name, max_tries=8):
    have = c.execute("SELECT n_points,last_day FROM history_meta WHERE name=? "
                     "AND n_points>0", (name,)).fetchone()
    if have:
        print(f"  {name:34s} cached {have[0]} pts -> {have[1]}", flush=True)
        return True
    caps = captures(name)
    if not caps:
        print(f"  {name:34s} no captures", flush=True)
        return False
    for ts in sorted(caps, reverse=True)[:max_tries]:
        url = (f"https://web.archive.org/web/{ts}id_/"
               f"https://steamcommunity.com/market/listings/730/"
               + urllib.parse.quote(name))
        try:
            html = _get(url)
        except Exception as e:
            print(f"  {name:34s} {ts} fetch {type(e).__name__}", flush=True)
            continue
        daily, nid = parse_line1(html)
        if not daily:
            continue
        rows = [(name, d, (s / n if n else None), n) for d, (s, n) in daily.items()]
        c.executemany("INSERT OR REPLACE INTO history(name,day,price_usd,volume) "
                      "VALUES(?,?,?,?)", rows)
        ds = sorted(daily)
        c.execute("INSERT OR REPLACE INTO history_meta(name,item_nameid,n_points,"
                  "first_day,last_day,fetched_ts,http_status) VALUES(?,?,?,?,?,?,?)",
                  (name, nid, len(ds), ds[0], ds[-1], int(time.time()), 200))
        c.commit()
        print(f"  {name:34s} capture {ts[:8]} -> {len(ds)} days "
              f"{ds[0]}..{ds[-1]}", flush=True)
        return True
    print(f"  {name:34s} captures exist but none carry line1", flush=True)
    return False


def main():
    c = db.connect()
    try:
        c.execute("ALTER TABLE history ADD COLUMN source TEXT DEFAULT 'wayback'")
    except sqlite3.OperationalError:
        pass
    names = sys.argv[1:]
    if not names:
        names = [n for (n,) in c.execute(
            "SELECT name FROM items WHERE class='case' ORDER BY name")]
    print(f"external history for {len(names)} items", flush=True)
    ok = 0
    for n in names:
        if fetch_item(c, n):
            ok += 1
    print(f"\ngot history for {ok}/{len(names)}", flush=True)
    c.close()


if __name__ == "__main__":
    main()
