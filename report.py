"""Counts, coverage, and the ranked table. Numbers only."""
import db


def fmt(v, spec=".2f", dash="-"):
    return dash if v is None else format(v, spec)


def pct(v):
    return "-" if v is None else f"{v * 100:+.1f}%"


def main():
    c = db.connect()
    q = c.execute

    print("=" * 100)
    print("COLLECTED")
    print("=" * 100)
    tot = q("SELECT COUNT(*) FROM items").fetchone()[0]
    print(f"Steam inventory pass (sell_listings):   {tot} items")
    if tot == 0:
        print("  ^ blocked: Steam has been answering 429 on every market endpoint.")
        print("    Everything below is archive-derived and needs no Steam access.")
    for cls, n in q("SELECT class,COUNT(*) FROM items GROUP BY class ORDER BY 2 DESC"):
        print(f"  {cls:18s} {n}")
    try:
        an = q("SELECT COUNT(*) FROM archive_names").fetchone()[0]
        print(f"archive name universe (no Steam needed): {an} market_hash_names")
    except Exception:
        pass
    print(f"items in the map:                       "
          f"{q('SELECT COUNT(*) FROM metrics').fetchone()[0]}")
    for cls, n in q("SELECT class,COUNT(*) FROM metrics GROUP BY class ORDER BY 2 DESC"):
        print(f"  {cls or '?':18s} {n}")

    print("\nmarket data coverage")
    for label, sql in [
        ("with listings snapshot", "SELECT COUNT(DISTINCT name) FROM snapshots WHERE sell_listings IS NOT NULL"),
        ("with 24h volume",        "SELECT COUNT(DISTINCT name) FROM snapshots WHERE volume_24h IS NOT NULL"),
        ("with any daily history", "SELECT COUNT(*) FROM history_meta WHERE n_points>0"),
        ("with >=3y history",      "SELECT COUNT(*) FROM metrics WHERE price_3y IS NOT NULL"),
        ("with >=2y history",      "SELECT COUNT(*) FROM metrics WHERE price_2y IS NOT NULL"),
        ("with >=1y history",      "SELECT COUNT(*) FROM metrics WHERE price_1y IS NOT NULL"),
        ("with supply_trend",      "SELECT COUNT(*) FROM metrics WHERE supply_trend IS NOT NULL"),
    ]:
        print(f"  {label:24s} {q(sql).fetchone()[0]}")

    print("\nstatus")
    for s, n in q("SELECT status,COUNT(*) FROM metrics GROUP BY status ORDER BY 2 DESC"):
        print(f"  {s:18s} {n}")

    dis = list(q("SELECT name,status_detail FROM metrics WHERE status='disputed' ORDER BY name"))
    if dis:
        print(f"\nSOURCE DISAGREEMENTS ({len(dis)}) -- not resolved, shown as-is")
        for n, d in dis:
            print(f"  {n:32s} {d}")

    b = q("SELECT baseline_cagr FROM metrics WHERE baseline_cagr IS NOT NULL "
          "LIMIT 1").fetchone()
    print("\n" + "=" * 108)
    print("TOP-30: supply drying up + price still behind the fixed-supply cohort line")
    if b:
        print(f"benchmark = median CAGR of legacy (non-active-drop) cases; "
              f"excess is measured against that, not against the market")
    print("=" * 108)
    rows = list(q("""SELECT name,class,status,price_now,listings_now,volume_30d,
                            vol_trend_1y,cagr,baseline_cagr,excess_cagr,
                            supply_trend,lag_score
                     FROM metrics
                     WHERE excess_cagr IS NOT NULL AND status != 'active_drop'
                     ORDER BY (CASE WHEN vol_trend_1y IS NULL THEN 1 ELSE 0 END),
                              (excess_cagr + COALESCE(vol_trend_1y,0)) ASC
                     LIMIT 30"""))
    if not rows:
        print("  EMPTY -- needs price history; see coverage above.")
    else:
        h = (f"{'#':>3} {'name':34s} {'class':8s} {'status':13s} {'price':>8s} "
             f"{'listings':>9s} {'vol30d':>9s} {'turnover':>9s} {'cagr':>8s} "
             f"{'excess':>8s} {'supply':>7s}")
        print(h)
        print("-" * len(h))
        for i, r in enumerate(rows, 1):
            print(f"{i:>3} {r[0][:34]:34s} {(r[1] or '?')[:8]:8s} {r[2][:13]:13s} "
                  f"{fmt(r[3]):>8s} "
                  f"{(format(r[4], 'd') if r[4] is not None else '-'):>9s} "
                  f"{(format(r[5], 'd') if r[5] is not None else '-'):>9s} "
                  f"{pct(r[6]):>9s} {pct(r[7]):>8s} {pct(r[9]):>8s} "
                  f"{pct(r[10]):>7s}")
        print("\n  listings/supply blank = Steam inventory pass has not run yet "
              "(429 lockout); turnover is the archive-derived stand-in.")
    c.close()


if __name__ == "__main__":
    main()
