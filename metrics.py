"""Derived layer. Every column states what it is computed from; anything without
an observation behind it stays NULL rather than being filled in.

supply_trend is defined as the change in sell_listings between the oldest and
newest snapshot of an item. Steam publishes no historical listing counts, so on
a first run there is exactly one snapshot and this column is NULL by
construction -- the run establishes t0. It is not substituted with a proxy;
vol_trend_1y is reported separately and is a different thing (turnover, not
stock).
"""
import csv
import math
import statistics as st
import time

import db
import status_load

DAY = 86400
NOW = time.time()


def window_price(hist, days_ago, halfwidth=10):
    """Median daily price in a +/-halfwidth window centred days_ago back."""
    lo, hi = days_ago - halfwidth, days_ago + halfwidth
    vals = [p for age, p, _ in hist if lo <= age <= hi and p]
    return st.median(vals) if vals else None


def window_volume(hist, days_ago, halfwidth=15):
    lo, hi = days_ago - halfwidth, days_ago + halfwidth
    v = [q for age, _, q in hist if lo <= age <= hi]
    return sum(v) if v else None


def cagr(now, then, years):
    if not now or not then or then <= 0 or now <= 0:
        return None
    try:
        return (now / then) ** (1.0 / years) - 1.0
    except (ValueError, OverflowError, ZeroDivisionError):
        return None


def pct_rank(vals):
    """value -> percentile in [0,1]; ties share the mean rank."""
    clean = sorted(v for v in vals if v is not None)
    n = len(clean)
    if n < 2:
        return lambda v: None
    def f(v):
        if v is None:
            return None
        lo = sum(1 for x in clean if x < v)
        eq = sum(1 for x in clean if x == v)
        return (lo + eq / 2.0) / n
    return f


def build(c):
    statuses = status_load.resolve(c)

    snaps = {}
    for name, ts, lst, price, med, vol in c.execute(
            "SELECT name,ts,sell_listings,price_usd,median_usd,volume_24h "
            "FROM snapshots ORDER BY name,ts"):
        snaps.setdefault(name, []).append((ts, lst, price, med, vol))

    asof = dict(c.execute("SELECT name,last_day FROM history_meta WHERE n_points>0"))

    hist = {}
    for name, day, price, vol in c.execute(
            "SELECT name,day,price_usd,volume FROM history"):
        t = time.mktime(time.strptime(day, "%Y-%m-%d"))
        hist.setdefault(name, []).append(((NOW - t) / DAY, price, vol or 0))

    # universe = everything inventoried, plus anything we have history for even
    # if the Steam inventory pass has not reached it yet
    items = {n: (cls, cap) for n, cls, cap in c.execute(
        "SELECT name,class,source_capsule FROM items")}
    from step1_inventory import classify
    for (n,) in c.execute("SELECT name FROM history_meta WHERE n_points>0"):
        items.setdefault(n, (classify(n, None)[0], None))

    rows = []
    for name, (cls, cap) in items.items():
        sn = snaps.get(name, [])
        last = sn[-1] if sn else (None, None, None, None, None)
        listings_now = last[1]
        price_now = last[2] if last[2] is not None else last[3]
        vol24 = last[4]

        # supply_trend: needs two real observations of sell_listings
        supply_trend, supply_basis = None, "single snapshot (t0 established)"
        obs = [(ts, l) for ts, l, *_ in sn if l is not None]
        if len(obs) >= 2 and obs[0][1]:
            span = (obs[-1][0] - obs[0][0]) / DAY
            if span >= 1:
                supply_trend = obs[-1][1] / obs[0][1] - 1.0
                supply_basis = (f"sell_listings {obs[0][1]}->{obs[-1][1]} "
                                f"over {span:.0f}d")

        h = sorted(hist.get(name, []))
        rel_year = None
        vol30 = vol30_1y = None
        p1 = p2 = p3 = None
        p_last = None
        if h:
            oldest = max(a for a, _, _ in h)
            newest = min(a for a, _, _ in h)
            rel_year = time.gmtime(NOW - oldest * DAY).tm_year
            # history is an archive snapshot, so "now" is its last day, not today
            vol30 = sum(q for a, _, q in h if a <= newest + 30)
            vol30_1y = window_volume(h, newest + 365)
            p1, p2, p3 = (window_price(h, newest + 365), window_price(h, newest + 730),
                          window_price(h, newest + 1095))
            p_last = window_price(h, newest, halfwidth=7)
        if price_now is None:
            price_now = p_last
        if vol30 is None and vol24 is not None:
            vol30 = None  # 24h*30 would be an invention, not an observation

        c1, c2, c3 = (cagr(price_now, p1, 1), cagr(price_now, p2, 2),
                      cagr(price_now, p3, 3))
        best = c3 if c3 is not None else (c2 if c2 is not None else c1)

        vt = None
        if vol30 is not None and vol30_1y:
            vt = vol30 / vol30_1y - 1.0

        flow30 = vol30 if vol30 is not None else (vol24 * 30 if vol24 else None)
        months = None
        if listings_now is not None and flow30:
            months = listings_now / flow30

        status, detail = statuses.get(name, ("unknown", "no source names this item"))

        conf = []
        conf.append("hist" if h else "nohist")
        conf.append("vol" if (vol24 is not None or vol30) else "novol")
        conf.append("status" if status not in ("unknown", "disputed") else status)
        rows.append(dict(
            name=name, cls=cls, cap=cap, rel_year=rel_year, status=status,
            detail=detail, price_now=price_now, listings_now=listings_now,
            volume_30d=vol30, volume_24h=vol24, p1=p1, p2=p2, p3=p3,
            c1=c1, c2=c2, c3=c3, cagr=best, supply_trend=supply_trend,
            supply_basis=supply_basis, months=months, vt=vt,
            as_of=asof.get(name), confidence="/".join(conf)))

    # Benchmark. The placebo test established that fixed-supply legacy items
    # outrun still-dropping ones in almost any quarter, so "did it beat the
    # market" is the wrong bar -- the bar is that cohort's own drift. Baseline =
    # median CAGR of legacy cases (anything not on active drop), per horizon.
    def baseline(key):
        v = [r[key] for r in rows
             if r["cls"] == "case" and r["status"] not in ("active_drop", "purchase_only")
             and r[key] is not None]
        return st.median(v) if len(v) >= 5 else None

    base = {k: baseline(k) for k in ("c1", "c2", "c3")}
    print("  cohort baseline CAGR (legacy cases): " + ", ".join(
        f"{k}={'-' if v is None else format(v, '+.1%')}" for k, v in base.items()))
    for r in rows:
        for horizon, key in (("c3", "c3"), ("c2", "c2"), ("c1", "c1")):
            if r[key] is not None and base[horizon] is not None:
                r["baseline_cagr"] = base[horizon]
                r["excess_cagr"] = r[key] - base[horizon]
                r["excess_horizon"] = {"c1": "1y", "c2": "2y", "c3": "3y"}[horizon]
                break
        else:
            r["baseline_cagr"] = r["excess_cagr"] = r["excess_horizon"] = None

    # lag_score: thin shelf relative to turnover + price that has lagged the
    # cohort line, ranked inside each class so cases are not compared to stickers.
    for cls in {r["cls"] for r in rows}:
        grp = [r for r in rows if r["cls"] == cls]
        tight = pct_rank([-(r["months"]) for r in grp if r["months"] is not None])
        lag = pct_rank([-(r["excess_cagr"]) for r in grp
                        if r["excess_cagr"] is not None])
        for r in grp:
            t = tight(-r["months"]) if r["months"] is not None else None
            l = lag(-r["excess_cagr"]) if r["excess_cagr"] is not None else None
            if t is not None and l is not None:
                r["lag_score"] = 0.5 * t + 0.5 * l
            elif t is not None:
                r["lag_score"] = None   # half a score is not a score
            else:
                r["lag_score"] = None

    c.execute("DELETE FROM metrics")
    c.executemany("""INSERT INTO metrics(name,class,source_capsule,release_year,status,
        status_detail,price_now,listings_now,volume_30d,price_1y,price_2y,price_3y,
        cagr_1y,cagr_2y,cagr_3y,cagr,supply_trend,supply_basis,months_supply,
        vol_trend_1y,baseline_cagr,excess_cagr,excess_horizon,lag_score,confidence,as_of)
        VALUES(:name,:cls,:cap,:rel_year,:status,:detail,:price_now,:listings_now,
        :volume_30d,:p1,:p2,:p3,:c1,:c2,:c3,:cagr,:supply_trend,:supply_basis,
        :months,:vt,:baseline_cagr,:excess_cagr,:excess_horizon,:lag_score,:confidence,:as_of)""", rows)
    c.commit()
    return rows


CSV_COLS = ["name", "class", "source_capsule", "release_year", "status", "price_now",
            "listings_now", "volume_30d", "price_1y", "price_2y", "price_3y", "cagr",
            "supply_trend", "confidence", "cagr_1y", "cagr_2y", "cagr_3y",
            "months_supply", "vol_trend_1y", "baseline_cagr", "excess_cagr",
            "excess_horizon", "lag_score", "as_of", "tournament", "tour_year",
            "age_years", "variant", "steam_liquidity", "offsteam_listings",
            "offsteam_median", "offsteam_censored", "price_ratio_off_steam",
            "supply_basis", "status_detail"]


def export_csv(c, path="/root/projects/supply-side/supply_map.csv"):
    cur = c.execute(f"SELECT {','.join(CSV_COLS)} FROM metrics ORDER BY class,name")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLS)
        w.writerows(cur)
    return path


def attach_offsteam(c):
    """Copy the freshest off-Steam reading onto metrics. Kept as its own columns:
    Steam volume is a monthly flow, off-Steam listings are a standing stock, and
    collapsing the two into one "liquidity" number hides which venue an item
    actually trades on."""
    for col, typ in (("offsteam_listings", "INTEGER"), ("offsteam_median", "REAL"),
                     ("offsteam_censored", "INTEGER"), ("price_ratio_off_steam", "REAL")):
        try:
            c.execute(f"ALTER TABLE metrics ADD COLUMN {col} {typ}")
        except Exception:
            pass
    n = 0
    for name, l, mdp, cen in c.execute(
            """SELECT name,listings,median_price,censored FROM offsteam o
               WHERE source='lis' AND ts=(SELECT MAX(ts) FROM offsteam
                                          WHERE name=o.name AND source='lis')"""):
        c.execute("""UPDATE metrics SET offsteam_listings=?, offsteam_median=?,
                     offsteam_censored=?,
                     price_ratio_off_steam=CASE WHEN price_now>0 AND ?>0
                                                THEN ?/price_now END
                     WHERE name=?""", (l, mdp, cen, mdp, mdp, name))
        n += 1
    c.commit()
    return n


if __name__ == "__main__":
    import lifecycle
    c = db.connect()
    rows = build(c)
    n_t, n = lifecycle.annotate(c)          # tournament / age / liquidity / variant
    n_off = attach_offsteam(c)
    p = export_csv(c)
    print(f"metrics rows: {len(rows)} ({n_t} with a tournament, "
          f"{n_off} with an off-Steam reading) -> {p}")
    c.close()
