"""Does the "stickers rise but cannot be sold" conclusion survive off-Steam data?

Steam's 30d volume measures sellability *on Steam*. Steam takes ~13% and pays
into a non-cashable wallet, so the cheap end (sub-dollar capsules) trades there
and the expensive end (holo / gold / autographs) trades on cash markets. The
bias therefore runs in one direction: Steam volume flatters cheap items and
starves expensive ones. That is exactly the axis the earlier "buy capsules, not
stickers" conclusion was drawn along, so it has to be re-tested.

Liquidity is reported as two columns, never merged: steam_volume_30d and
offsteam_listings. They measure different things -- a flow (units sold per
month) versus a stock (units on the shelf right now) -- and averaging them would
be meaningless.
"""
import statistics as st
from collections import defaultdict

import db

PRICE_BUCKETS = [(0, 1, "<$1"), (1, 5, "$1-5"), (5, 20, "$5-20"),
                 (20, 100, "$20-100"), (100, 1e9, ">$100")]


def f(v, spec=".1f"):
    if v is None:
        return "-"
    if spec.startswith("$"):
        return "$" + format(v, spec[1:])
    return format(v, spec)


def med(v):
    v = [x for x in v if x is not None]
    return st.median(v) if v else None


def load(c):
    off = {}
    for name, l, mn, mdp, cen in c.execute(
            """SELECT name,listings,min_price,median_price,censored FROM offsteam o
               WHERE source='lis' AND ts=(SELECT MAX(ts) FROM offsteam
                                          WHERE name=o.name AND source='lis')"""):
        off[name] = dict(listings=l, min_price=mn, median=mdp, censored=cen)
    rows = []
    for (name, cls, variant, price, vol, cagr, tour, age, liq) in c.execute(
            """SELECT name,class,variant,price_now,volume_30d,cagr,tournament,
                      age_years,liquidity FROM metrics
               WHERE class IN ('sticker','capsule')"""):
        o = off.get(name)
        rows.append(dict(name=name, cls=cls, variant=variant, price=price,
                         steam_vol=vol, cagr=cagr, tour=tour, age=age, liq=liq,
                         off_listings=(o or {}).get("listings"),
                         off_med=(o or {}).get("median"),
                         off_min=(o or {}).get("min_price"),
                         censored=(o or {}).get("censored")))
    return rows, off


def bucket(p):
    for lo, hi, lbl in PRICE_BUCKETS:
        if p is not None and lo <= p < hi:
            return lbl
    return None


def by_price_class(rows):
    print(f"  {'price band':11s} {'n':>3s} {'med steam vol30d':>17s} "
          f"{'med LIS listings':>17s} {'ratio LIS/steam':>16s} {'censored':>9s}")
    g = defaultdict(list)
    for r in rows:
        b = bucket(r["price"])
        if b and r["off_listings"] is not None:
            g[b].append(r)
    for _, _, lbl in PRICE_BUCKETS:
        rs = g.get(lbl)
        if not rs:
            continue
        sv = med([x["steam_vol"] for x in rs])
        ol = med([x["off_listings"] for x in rs])
        ratio = (ol / sv) if (sv and ol is not None and sv > 0) else None
        cen = sum(1 for x in rs if x["censored"])
        print(f"  {lbl:11s} {len(rs):>3d} {f(sv, ',.0f'):>17s} {f(ol, ',.0f'):>17s} "
              f"{f(ratio, '.3f'):>16s} {cen:>4d}/{len(rs)}")
    print("  ratio = off-Steam stock on the shelf per unit of monthly Steam flow.")
    print("  Higher = more of that item's life happens away from Steam.")


def by_variant(rows):
    print(f"  {'class/variant':16s} {'n':>3s} {'med price':>10s} "
          f"{'med steam vol':>14s} {'med LIS listings':>17s} {'on LIS':>8s}")
    g = defaultdict(list)
    for r in rows:
        k = r["variant"] if r["cls"] == "sticker" and r["variant"] else r["cls"]
        if r["off_listings"] is not None:
            g[k].append(r)
    for k in ("capsule", "Paper", "Foil", "Holo", "Gold", "Glitter"):
        rs = g.get(k)
        if not rs:
            continue
        on = sum(1 for x in rs if x["off_listings"])
        print(f"  {k:16s} {len(rs):>3d} {f(med([x['price'] for x in rs]), '$.2f'):>10s} "
              f"{f(med([x['steam_vol'] for x in rs]), ',.0f'):>14s} "
              f"{f(med([x['off_listings'] for x in rs]), ',.0f'):>17s} "
              f"{on:>4d}/{len(rs)}")


def price_gap(rows):
    g = [r for r in rows if r["price"] and r["off_med"]]
    if not g:
        print("  no overlapping prices yet")
        return
    print(f"  {'class/variant':16s} {'n':>3s} {'med steam $':>12s} {'med LIS $':>11s} "
          f"{'LIS/Steam':>10s}")
    by = defaultdict(list)
    for r in g:
        by[r["variant"] if r["cls"] == "sticker" and r["variant"] else r["cls"]].append(r)
    for k, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        ratios = [x["off_med"] / x["price"] for x in rs if x["price"]]
        print(f"  {k:16s} {len(rs):>3d} "
              f"{f(med([x['price'] for x in rs]), '$.2f'):>12s} "
              f"{f(med([x['off_med'] for x in rs]), '$.2f'):>11s} "
              f"{f(med(ratios), '.2f'):>10s}")
    allr = [x["off_med"] / x["price"] for x in g if x["price"]]
    print(f"  overall median LIS/Steam price ratio: {f(med(allr), '.2f')}  (n={len(allr)})")


def verdict(rows, thin_steam=500, thin_off=5):
    """Point 5, both ways."""
    g = [r for r in rows if r["cagr"] is not None]
    g.sort(key=lambda r: -r["cagr"])
    print(f"  {'#':>3} {'name':40s} {'cls':7s} {'var':7s} {'CAGR':>8s} {'price':>9s} "
          f"{'steam_vol_30d':>13s} {'offsteam_listings':>17s} {'verdict':>22s}")
    for i, r in enumerate(g[:25], 1):
        sv, ol = r["steam_vol"], r["off_listings"]
        steam_thin = sv is not None and sv < thin_steam
        off_thin = ol is not None and ol < thin_off
        if ol is None:
            v = "off-Steam not measured"
        elif steam_thin and off_thin:
            v = "illiquid both venues"
        elif steam_thin and not off_thin:
            v = "trades OFF Steam"
        elif not steam_thin and off_thin:
            v = "Steam-only"
        else:
            v = "liquid both"
        print(f"  {i:>3} {r['name'][:40]:40s} {r['cls'][:7]:7s} "
              f"{(r['variant'] or '-')[:7]:7s} {f(r['cagr'], '.1%'):>8s} "
              f"{f(r['price'], '$.2f'):>9s} {f(sv, ',.0f'):>13s} "
              f"{(f(ol, ',.0f') + ('+' if r['censored'] else '')):>17s} {v:>22s}")


if __name__ == "__main__":
    c = db.connect()
    rows, off = load(c)
    n_off = sum(1 for r in rows if r["off_listings"] is not None)
    print(f"items: {len(rows)} | with off-Steam reading: {n_off}")
    print("\n=== 1. off-Steam stock vs Steam flow, by price band ===")
    by_price_class(rows)
    print("\n=== 2. by class / sticker variant ===")
    by_variant(rows)
    print("\n=== 3. price gap: LIS vs Steam ===")
    price_gap(rows)
    print("\n=== 4. point 5 recomputed, liquidity split into two columns ===")
    verdict(rows)
    c.close()
