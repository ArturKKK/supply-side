"""Primary-source check: Valve's own CS2 update feed.

api.steampowered.com/ISteamNews is the same feed the in-game / counter-strike.net
update list is built from. No login, separate host from the market, so it is not
affected by the market rate limit. We store every post in the window and grep the
verbatim text -- if Valve never said it, that is itself the finding.
"""
import json
import re
import sys
import time
import urllib.request

URL = ("https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
       "?appid=730&count=500&maxlength=20000&format=json")
OUT = "/root/projects/supply-side/data/valve_cs2_news.json"

KEYWORDS = ["case", "container", "drop", "care package", "weekly", "reward",
            "rare", "capsule", "pool"]


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "supply-side/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def strip(s):
    s = re.sub(r"\[/?[^\]]+\]", " ", s)          # bbcode
    s = re.sub(r"<[^>]+>", " ", s)               # html
    return re.sub(r"\s+", " ", s).strip()


def main():
    data = fetch()
    items = data["appnews"]["newsitems"]
    json.dump(items, open(OUT, "w"), indent=1)
    print(f"posts fetched: {len(items)}  -> {OUT}")
    if items:
        oldest = time.strftime('%Y-%m-%d', time.gmtime(min(i['date'] for i in items)))
        newest = time.strftime('%Y-%m-%d', time.gmtime(max(i['date'] for i in items)))
        print(f"feed covers: {oldest} .. {newest}")

    lo = time.mktime(time.strptime("2025-11-01", "%Y-%m-%d"))
    hi = time.mktime(time.strptime("2026-03-01", "%Y-%m-%d"))
    win = sorted([i for i in items if lo <= i["date"] <= hi], key=lambda i: i["date"])
    print(f"\nposts in 2025-11-01 .. 2026-03-01: {len(win)}")
    print("-" * 96)
    hits = 0
    for i in win:
        d = time.strftime("%Y-%m-%d", time.gmtime(i["date"]))
        body = strip(i.get("contents", ""))
        found = [k for k in KEYWORDS if re.search(rf"\b{k}\b", body, re.I)]
        mark = "*" if found else " "
        if found:
            hits += 1
        print(f"{mark} {d}  {i.get('title','')[:58]:58s} {i.get('feedlabel','')[:14]:14s} "
              f"{','.join(found) if found else '-'}")
    print("-" * 96)
    print(f"posts in window mentioning any drop/case keyword: {hits}")

    print("\n=== verbatim sentences containing the keywords, in window ===")
    n = 0
    for i in win:
        body = strip(i.get("contents", ""))
        d = time.strftime("%Y-%m-%d", time.gmtime(i["date"]))
        for sent in re.split(r"(?<=[.!?])\s+", body):
            if re.search(r"\b(drop|case|container|care package|rare)\b", sent, re.I):
                print(f"  [{d}] {sent[:300]}")
                n += 1
    if n == 0:
        print("  NONE. Valve's feed says nothing about cases/drops in this window.")


if __name__ == "__main__":
    sys.exit(main())
