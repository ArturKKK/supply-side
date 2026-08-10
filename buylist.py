"""Final sticker buy list. Filters are applied in the order the brief fixes them,
each one only to what survived the previous, so the funnel is a real funnel.

Age is measured from the tournament YEAR to today, not from the item's archive
as_of date -- metrics.age_years is anchored to as_of, which makes it a function
of how fresh the Wayback capture is rather than of the item. Year granularity is
all the name carries; the exact tournament date is not derivable from it.
"""
import datetime as dt
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "/root/projects/supply-side")
import lifecycle
import stickers

DB = "file:/root/projects/supply-side/supply.db?mode=ro"
TARGETS = "/root/projects/supply-side/data/sticker_targets.txt"
MIN_LISTINGS = 3
MIN_AGE = 4.0
KEEP_VARIANTS = ("Holo", "Foil", "Paper")
MIN_HIST_YEARS = 3.0

TODAY = dt.date.today()
NOW_FRAC = TODAY.year + (TODAY.month - 1) / 12.0


def load():
    c = sqlite3.connect(DB, uri=True)
    off = {n: dict(listings=l, median=m, censored=cen, ts=ts)
           for n, l, m, cen, ts in c.execute(
               """SELECT name,listings,median_price,censored,ts FROM offsteam o
                  WHERE source='lis' AND ts=(SELECT MAX(ts) FROM offsteam
                                             WHERE name=o.name AND source='lis')""")}
    met = {n: dict(price=p, vol=v, cagr3=c3, as_of=a) for n, p, v, c3, a in c.execute(
        "SELECT name,price_now,volume_30d,cagr_3y,as_of FROM metrics")}
    hist = {}
    for n, fd, ld, np_ in c.execute(
            "SELECT name,first_day,last_day,n_points FROM history_meta WHERE n_points>0"):
        d0, d1 = dt.date.fromisoformat(fd), dt.date.fromisoformat(ld)
        hist[n] = dict(years=(d1 - d0).days / 365.25, first=fd, last=ld, n=np_)
    c.close()

    rows = []
    for name in (l.rstrip("\n") for l in open(TARGETS) if l.strip()):
        tour, year = lifecycle.tournament_of(name)
        p = stickers.parse(name)
        o, m, h = off.get(name, {}), met.get(name, {}), hist.get(name, {})
        rows.append(dict(
            name=name, tour=tour, year=year,
            variant=(p or {}).get("variant"),
            age=(NOW_FRAC - year) if year else None,
            off=o.get("listings"), off_med=o.get("median"), cen=o.get("censored"),
            steam_price=m.get("price"), steam_vol=m.get("vol"),
            cagr3=m.get("cagr3"), as_of=m.get("as_of"),
            hist_years=h.get("years")))
    return rows


def main():
    rows = load()
    n0 = len(rows)

    # (a) live order book off Steam -- a cut, not a tiebreak
    a_pass = [r for r in rows if r["off"] is not None and r["off"] >= MIN_LISTINGS]
    cut_a = n0 - len(a_pass)

    # (b) closed major, item at least MIN_AGE years old
    b_pass = [r for r in a_pass if r["age"] is not None and r["age"] >= MIN_AGE]
    cut_b = len(a_pass) - len(b_pass)

    # (c) variant
    c_pass = [r for r in b_pass if r["variant"] in KEEP_VARIANTS]
    cut_c = len(b_pass) - len(c_pass)

    # (d) rank on 3y CAGR. Under three years of history the number is not
    # computed from a three-year base, so it is reported as unknown rather than
    # extrapolated -- those rows are held out of the ranking, not ranked as zero.
    for r in c_pass:
        r["known"] = (r["cagr3"] is not None and r["hist_years"] is not None
                      and r["hist_years"] >= MIN_HIST_YEARS)
    ranked = sorted([r for r in c_pass if r["known"]], key=lambda r: -r["cagr3"])
    unknown = [r for r in c_pass if not r["known"]]
    return rows, a_pass, b_pass, c_pass, ranked, unknown, (n0, cut_a, cut_b, cut_c)


def fmt(v, spec, dash="unknown"):
    if v is None:
        return dash
    if spec.startswith("$"):
        return "$" + format(v, spec[1:])
    return format(v, spec)


if __name__ == "__main__":
    rows, a_pass, b_pass, c_pass, ranked, unknown, funnel = main()
    n0, cut_a, cut_b, cut_c = funnel
    print("universe (sticker targets with a LIS reading): %d" % n0)
    print("after (a) offsteam_listings>=3 : %d   cut %d" % (len(a_pass), cut_a))
    print("after (b) closed major, age>=4y: %d   cut %d" % (len(b_pass), cut_b))
    print("after (c) Holo/Foil/Paper      : %d   cut %d" % (len(c_pass), cut_c))
    print("  of which rankable on 3y CAGR : %d   (unknown, <3y history: %d)"
          % (len(ranked), len(unknown)))

    print("\n=== TABLE (top 25 by 3y CAGR) ===")
    hdr = ("name", "tour", "yr", "var", "off_lst", "steam_v30", "LIS $", "Steam $", "as_of", "CAGR3y", "hist_y")
    print("%-42s %-18s %4s %-5s %8s %10s %10s %10s %11s %9s %7s" % hdr)
    for r in ranked[:25]:
        print("%-42s %-18s %4d %-5s %8s %10s %10s %10s %11s %9s %7s" % (
            r["name"][:42], (r["tour"] or "unknown")[:18], r["year"], r["variant"],
            (str(r["off"]) + ("+" if r["cen"] else "")),
            fmt(r["steam_vol"], ",.0f"), fmt(r["off_med"], "$,.2f"),
            fmt(r["steam_price"], "$,.2f"), r["as_of"] or "unknown",
            fmt(r["cagr3"], "+.1%"), fmt(r["hist_years"], ".1f")))

    print("\n=== (a) survivors by variant ===")
    cv = Counter(r["variant"] for r in a_pass)
    for v in ("Holo", "Foil", "Paper", "Gold", "Glitter"):
        tot = sum(1 for r in rows if r["variant"] == v)
        print("  %-8s %3d of %3d" % (v, cv.get(v, 0), tot))
