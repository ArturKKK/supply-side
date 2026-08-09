"""Steam-free name discovery.

The Wayback CDX index can be walked by URL prefix, which yields every CS2 market
item whose listing page was ever archived -- real `market_hash_name` values, no
guessing. This does NOT give sell_listings or price (only Steam has those), but
it gives a target list to collect archived history for while Steam is locked out,
and a cross-check on the names our sources claim exist.
"""
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

import db

UA = {"User-Agent": "supply-side/1.0 (one-off research)"}
PREFIX = "steamcommunity.com/market/listings/730/"
BASE = ("http://web.archive.org/cdx/search/cdx?url={u}&matchType=prefix"
        "&output=json&filter=statuscode:200&collapse=urlkey&fl=original,timestamp"
        "&page={p}")


def get(url, tries=4, timeout=240):
    last = None
    for i in range(tries):
        time.sleep(4 * (1 + i * 2))
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=timeout).read()
        except Exception as e:
            last = e
            print(f"    archive {type(e).__name__} (try {i + 1}/{tries})", flush=True)
    raise last


def npages(u):
    q = f"http://web.archive.org/cdx/search/cdx?url={u}&matchType=prefix&showNumPages=true"
    return int(get(q, timeout=90).decode().strip())


def main():
    c = db.connect()
    c.execute("""CREATE TABLE IF NOT EXISTS archive_names (
                    name TEXT PRIMARY KEY, last_capture TEXT, found_ts INTEGER)""")
    c.commit()
    u = urllib.parse.quote(PREFIX, safe="")
    total = npages(u)
    print(f"CDX pages: {total}", flush=True)
    done = {int(v) for (k, v) in c.execute(
        "SELECT k,v FROM run_meta WHERE k LIKE 'cdx:page:%'")
        for _ in [0]} if False else set()
    for (k,) in c.execute("SELECT k FROM run_meta WHERE k LIKE 'cdx:page:%'"):
        done.add(int(k.split(":")[-1]))

    for p in range(total):
        if p in done:
            continue
        try:
            raw = get(BASE.format(u=u, p=p))
        except Exception as e:
            print(f"  page {p}: giving up ({type(e).__name__})", flush=True)
            continue
        rows, n = [], 0
        for line in raw.decode("utf-8", "ignore").splitlines():
            m = re.search(r'"(https?://[^"]*?/market/listings/730/[^"]+)"\s*,\s*"(\d{14})"',
                          line)
            if not m:
                continue
            nm = urllib.parse.unquote(urllib.parse.unquote(
                m.group(1).split("/market/listings/730/")[-1])).split("?")[0].strip()
            if not nm or len(nm) > 200:
                continue
            rows.append((nm, m.group(2), int(time.time())))
            n += 1
        c.executemany("INSERT OR IGNORE INTO archive_names(name,last_capture,found_ts) "
                      "VALUES(?,?,?)", rows)
        c.execute("INSERT OR REPLACE INTO run_meta(k,v) VALUES(?,?)",
                  (f"cdx:page:{p}", str(n)))
        c.commit()
        tot = c.execute("SELECT COUNT(*) FROM archive_names").fetchone()[0]
        print(f"  page {p + 1}/{total}: +{n} rows, {tot} distinct names", flush=True)

    tot = c.execute("SELECT COUNT(*) FROM archive_names").fetchone()[0]
    print(f"\ndistinct archived CS2 market names: {tot}", flush=True)
    for lbl, like in (("capsule", "%apsule%"), ("case", "% Case%"),
                      ("sticker", "Sticker |%"), ("package", "%Souvenir Package%")):
        n = c.execute("SELECT COUNT(*) FROM archive_names WHERE name LIKE ?",
                      (like,)).fetchone()[0]
        print(f"  {lbl:10s} {n}")
    c.close()


if __name__ == "__main__":
    main()
