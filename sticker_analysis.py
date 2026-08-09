"""Two questions the brief asks, answered by variant and by tournament.

  A. do rarer variants (Holo / Gold / Foil) appreciate faster than Paper?
  B. does the capsule or the sticker out of it grow faster?

B is answered at the tournament level, not by pairing an individual sticker to
the exact capsule that produced it: that mapping lives in Steam's StickerCapsule
facet, which is unreachable while Steam is refusing requests, and guessing it
from names would be invention. Tournament-level is the comparison an actual
buying decision is made at anyway -- "Krakow capsules or Krakow stickers".
"""
import statistics as st
from collections import defaultdict

import db
import stickers

VAR_ORDER = ["Paper", "Foil", "Holo", "Gold", "Glitter"]


def med(v):
    v = [x for x in v if x is not None]
    return st.median(v) if v else None


def fmt(v, spec=".1%"):
    if v is None:
        return "-"
    if spec.startswith("$"):
        return "$" + format(v, spec[1:])
    return format(v, spec)


def by_variant(c):
    rows = list(c.execute("""SELECT variant,tournament,tour_year,cagr,price_now,
                                    volume_30d,vol_trend_1y,liquidity
                             FROM metrics WHERE class='sticker' AND variant IS NOT NULL"""))
    if not rows:
        print("  no sticker history yet")
        return
    old = set(stickers.OLD_MAJORS)
    new = set(stickers.NEW_MAJORS)
    print(f"  {'variant':9s} {'era':16s} {'n':>3s} {'med CAGR':>9s} {'med price':>10s} "
          f"{'med vol30d':>11s} {'med turnover':>13s}")
    for era_name, era in (("closed 2016-19", old), ("recent 2023-25", new),
                          ("mid 2021-22", set(stickers.MID_MAJORS))):
        for v in VAR_ORDER:
            g = [r for r in rows if r[0] == v and r[1] in era]
            if not g:
                continue
            print(f"  {v:9s} {era_name:16s} {len(g):>3d} "
                  f"{fmt(med([x[3] for x in g])):>9s} "
                  f"{fmt(med([x[4] for x in g]), '$.2f'):>10s} "
                  f"{fmt(med([x[5] for x in g]), ',.0f'):>11s} "
                  f"{fmt(med([x[6] for x in g])):>13s}")


def capsule_vs_stickers(c):
    caps = defaultdict(list)
    stk = defaultdict(lambda: defaultdict(list))
    for name, cls, tour, cagr, price, vol, liq, age in c.execute(
            """SELECT name,class,tournament,cagr,price_now,volume_30d,liquidity,age_years
               FROM metrics WHERE tournament IS NOT NULL"""):
        if cls == "capsule":
            caps[tour].append((cagr, price, vol, liq, age))
        elif cls == "sticker":
            v = c.execute("SELECT variant FROM metrics WHERE name=?", (name,)).fetchone()
            stk[tour][v[0] if v else "?"].append((cagr, price, vol, liq, age))

    tours = sorted(set(caps) | set(stk),
                   key=lambda t: -(caps[t][0][4] if caps.get(t) and caps[t][0][4]
                                   else (stk[t][list(stk[t])[0]][0][4]
                                         if stk.get(t) else 0) or 0))
    print(f"  {'tournament':18s} {'age':>4s} | {'capsule':>18s} | "
          f"{'stickers by variant (median CAGR / median price)':<50s}")
    print("  " + "-" * 104)
    for t in tours:
        cg = caps.get(t, [])
        age = med([x[4] for x in cg]) if cg else med(
            [x[4] for vv in stk.get(t, {}).values() for x in vv])
        cap_s = (f"{fmt(med([x[0] for x in cg])):>7s} {fmt(med([x[1] for x in cg]), '$.2f'):>9s}"
                 if cg else f"{'no data':>17s}")
        parts = []
        for v in VAR_ORDER:
            g = stk.get(t, {}).get(v)
            if g:
                parts.append(f"{v}:{fmt(med([x[0] for x in g]))}/"
                             f"{fmt(med([x[1] for x in g]), '$.2f')}")
        print(f"  {t[:18]:18s} {(f'{age:.1f}' if age else '-'):>4s} | {cap_s} | "
              f"{', '.join(parts) if parts else '-'}")


if __name__ == "__main__":
    c = db.connect()
    n = c.execute("SELECT COUNT(*) FROM metrics WHERE class='sticker'").fetchone()[0]
    print(f"=== A. variant vs appreciation  (stickers with history: {n}) ===")
    by_variant(c)
    print("\n=== B. capsule vs the stickers of the same tournament ===")
    capsule_vs_stickers(c)
    c.close()
