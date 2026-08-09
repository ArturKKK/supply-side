"""Tournament and lifecycle stage, parsed out of the market name.

A capsule or sticker carries its tournament in its own name ("Krakow 2017
Legends Sticker Capsule", "Sticker | Astralis (Holo) | Krakow 2017"), and the
tournament name carries the year. `age` is then the years between that year and
the item's own as_of date -- both observed, neither looked up.

The year a tournament ran is *not* the year its capsule stopped being sold, and
this module does not pretend otherwise: `age` is years-since-tournament, which
is a lower bound on years-since-distribution-closed.
"""
import html
import re

import db
import stickers

TOUR_TOKENS = (stickers.OLD_MAJORS + stickers.NEW_MAJORS + stickers.MID_MAJORS +
               ["Cologne 2015", "Cluj-Napoca 2015", "Katowice 2015", "Katowice 2014",
                "Cologne 2014", "DreamHack 2014", "2020 RMR", "Columbus 2016"])


def tournament_of(name):
    """-> (tournament, year) or (None, None). Name-derived only."""
    n = html.unescape(name)
    p = stickers.parse(n)
    if p:
        return p["tournament"], p["year"]
    for t in TOUR_TOKENS:
        if t.lower() in n.lower():
            y = re.search(r"(19|20)\d{2}", t)
            return t, int(y.group(0)) if y else None
    m = re.match(r"^((?:[A-Z][\w.-]*\s+){0,3}?)((?:19|20)\d{2})\b", n)
    if m and m.group(1).strip():
        y = int(m.group(2))
        # a "year" in the future is part of a product name, not a date
        # ("Battlefield 2042"), so it is not treated as one
        if 2013 <= y <= 2026:
            return f"{m.group(1).strip()} {m.group(2)}", y
    return None, None


def annotate(c):
    """Fill tournament / tour_year / age / liquidity on the metrics table."""
    for col, typ in (("tournament", "TEXT"), ("tour_year", "INTEGER"),
                     ("age_years", "REAL"), ("liquidity", "TEXT"),
                     ("variant", "TEXT")):
        try:
            c.execute(f"ALTER TABLE metrics ADD COLUMN {col} {typ}")
        except Exception:
            pass
    rows = list(c.execute("SELECT name,as_of,volume_30d FROM metrics"))
    n_t = 0
    for name, as_of, vol in rows:
        tour, year = tournament_of(name)
        p = stickers.parse(name)
        variant = p["variant"] if p else None
        age = None
        if year and as_of:
            age = int(as_of[:4]) + (int(as_of[5:7]) - 1) / 12.0 - year
        if tour:
            n_t += 1
        liq = None
        if vol is not None:
            liq = "thin" if vol < 500 else ("ok" if vol < 20000 else "deep")
        c.execute("""UPDATE metrics SET tournament=?,tour_year=?,age_years=?,
                     liquidity=?,variant=? WHERE name=?""",
                  (tour, year, age, liq, variant, name))
    c.commit()
    return n_t, len(rows)


def curve(c, cls=None):
    """Price / turnover against years since the tournament."""
    where = "WHERE age_years IS NOT NULL"
    if cls:
        where += f" AND class='{cls}'"
    rows = list(c.execute(f"""SELECT name,class,tournament,age_years,price_now,
                                     volume_30d,vol_trend_1y,cagr,liquidity
                              FROM metrics {where} ORDER BY age_years DESC"""))
    return rows


if __name__ == "__main__":
    c = db.connect()
    n_t, n = annotate(c)
    print(f"tournament parsed for {n_t}/{n} items")
    import statistics as st
    from collections import defaultdict
    for cls in ("capsule", "sticker"):
        rows = curve(c, cls)
        if not rows:
            continue
        print(f"\n=== {cls}: lifecycle by years since tournament ===")
        buck = defaultdict(list)
        for r in rows:
            buck[int(r[3] // 2) * 2].append(r)
        print(f"  {'age':>7s} {'n':>3s} {'med price':>10s} {'med vol30d':>11s} "
              f"{'med turnover':>13s} {'med CAGR':>9s}")
        for a in sorted(buck, reverse=True):
            g = buck[a]
            pr = [x[4] for x in g if x[4]]
            vo = [x[5] for x in g if x[5] is not None]
            tu = [x[6] for x in g if x[6] is not None]
            cg = [x[7] for x in g if x[7] is not None]
            print(f"  {a:>3d}-{a + 2:<3d} {len(g):>3d} "
                  f"{(f'${st.median(pr):.2f}' if pr else '-'):>10s} "
                  f"{(f'{st.median(vo):,.0f}' if vo else '-'):>11s} "
                  f"{(f'{st.median(tu):+.1%}' if tu else '-'):>13s} "
                  f"{(f'{st.median(cg):+.1%}' if cg else '-'):>9s}")
    c.close()
