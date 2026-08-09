"""Sticker analysis: variant, tournament, lifecycle, spread, liquidity.

Standing caveat that colours everything below. The Internet Archive does not
sample the market at random -- it captures pages people look at. Expensive
autograph stickers get archived *because* they are stared at, so any statistic
computed over "stickers we could recover history for" is biased toward the
watched ones. Section 0 measures that bias directly (coverage rate per variant)
instead of assuming it away, and every CAGR is shown with its spread and its
turnover so a number resting on five trades a month is visible as such.

Section B compares capsules to stickers at the *tournament* level. Pairing an
individual sticker to the exact capsule that produced it needs Steam's
StickerCapsule facet, which is unreachable while Steam refuses requests;
inferring it from names would be invention.
"""
import statistics as st
from collections import defaultdict

import db
import stickers

VAR_ORDER = ["Paper", "Foil", "Holo", "Gold", "Glitter"]
THIN = 500          # units per 30d below which an exit is doubtful


def q(v, p):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    if len(v) == 1:
        return v[0]
    i = (len(v) - 1) * p
    lo, hi = int(i), min(int(i) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def med(v):
    return q(v, 0.5)


def f(v, spec=".1%"):
    if v is None:
        return "-"
    if spec.startswith("$"):
        return "$" + format(v, spec[1:])
    return format(v, spec)


# ---------------------------------------------------------------- section 0
def coverage(c):
    """How much of what we asked for did the archive actually have, per variant?
    This is the selection bias, measured rather than assumed."""
    targets = [l.strip() for l in
               open("/root/projects/supply-side/data/sticker_targets.txt") if l.strip()]
    got = {n for (n,) in c.execute(
        "SELECT name FROM history_meta WHERE n_points>0")}
    per = defaultdict(lambda: [0, 0])
    for t in targets:
        p = stickers.parse(t)
        if not p:
            continue
        per[p["variant"]][0] += 1
        if t in got:
            per[p["variant"]][1] += 1
    print(f"  {'variant':9s} {'asked':>6s} {'got':>5s} {'coverage':>9s}")
    for v in VAR_ORDER:
        if v in per:
            a, g = per[v]
            print(f"  {v:9s} {a:>6d} {g:>5d} {g / a:>9.0%}")
    print("  low coverage on a variant means its numbers rest on the subset the")
    print("  archive happened to keep, which skews toward the watched items.")


# ---------------------------------------------------------------- section A
def by_variant(c):
    rows = list(c.execute("""SELECT variant,tournament,cagr,price_now,volume_30d,
                                    vol_trend_1y,liquidity
                             FROM metrics WHERE class='sticker' AND variant IS NOT NULL"""))
    if not rows:
        print("  no sticker history yet")
        return
    eras = (("closed 2016-19", set(stickers.OLD_MAJORS)),
            ("mid 2021-22", set(stickers.MID_MAJORS)),
            ("recent 2023-25", set(stickers.NEW_MAJORS)))
    print(f"  {'variant':8s} {'era':15s} {'n':>3s} {'CAGR Q1':>8s} {'CAGR med':>9s} "
          f"{'CAGR Q3':>8s} {'med price':>10s} {'med vol30d':>11s} {'thin':>5s}")
    for era_name, era in eras:
        for v in VAR_ORDER:
            g = [r for r in rows if r[0] == v and r[1] in era]
            if not g:
                continue
            cg = [x[2] for x in g]
            vol = [x[4] for x in g]
            thin = sum(1 for x in g if x[4] is not None and x[4] < THIN)
            print(f"  {v:8s} {era_name:15s} {len(g):>3d} {f(q(cg, .25)):>8s} "
                  f"{f(med(cg)):>9s} {f(q(cg, .75)):>8s} "
                  f"{f(med([x[3] for x in g]), '$.2f'):>10s} "
                  f"{f(med(vol), ',.0f'):>11s} {thin:>3d}/{len(g)}")


# ---------------------------------------------------------------- section B
def capsule_vs_stickers(c):
    capg, stkg = defaultdict(list), defaultdict(list)
    for cls, tour, cagr, price, vol, age in c.execute(
            """SELECT class,tournament,cagr,price_now,volume_30d,age_years
               FROM metrics WHERE tournament IS NOT NULL AND cagr IS NOT NULL"""):
        if cls == "capsule":
            capg[tour].append((cagr, price, vol, age))
        elif cls == "sticker":
            stkg[tour].append((cagr, price, vol, age))

    both = sorted(set(capg) & set(stkg),
                  key=lambda t: -(med([x[3] for x in capg[t]]) or 0))
    print(f"  {'tournament':18s} {'age':>4s} {'nCap':>4s} {'nStk':>4s} "
          f"{'capsule CAGR':>13s} {'sticker CAGR':>13s} {'verdict':>16s}")
    agree = disagree = 0
    for t in both:
        cc, ss = med([x[0] for x in capg[t]]), med([x[0] for x in stkg[t]])
        age = med([x[3] for x in capg[t]])
        if cc is None or ss is None:
            continue
        if ss > cc:
            verdict, agree = "stickers win", agree + 1
        else:
            verdict, disagree = "CAPSULE wins", disagree + 1
        print(f"  {t[:18]:18s} {(f'{age:.1f}' if age else '-'):>4s} "
              f"{len(capg[t]):>4d} {len(stkg[t]):>4d} {f(cc):>13s} {f(ss):>13s} "
              f"{verdict:>16s}")
    if agree or disagree:
        print(f"\n  tournaments where stickers beat the capsule: {agree}/"
              f"{agree + disagree}; where the capsule wins: {disagree}")
    only = sorted(set(capg) - set(stkg))
    if only:
        print(f"  ({len(only)} tournaments have capsule history but no sticker "
              f"history yet)")


# ---------------------------------------------------------------- section C
def lifecycle(c, cls):
    rows = list(c.execute(f"""SELECT age_years,price_now,volume_30d,vol_trend_1y,cagr
                              FROM metrics WHERE class='{cls}' AND age_years IS NOT NULL"""))
    if not rows:
        print(f"  no {cls} data with an age yet")
        return
    buck = defaultdict(list)
    for r in rows:
        buck[int(r[0] // 2) * 2].append(r)
    print(f"  {'age':>7s} {'n':>3s} {'med price':>10s} {'med vol30d':>11s} "
          f"{'med turnover':>13s} {'CAGR Q1':>8s} {'CAGR med':>9s} {'CAGR Q3':>8s}")
    for a in sorted(buck, reverse=True):
        g = buck[a]
        cg = [x[4] for x in g]
        print(f"  {a:>3d}-{a + 2:<3d} {len(g):>3d} "
              f"{f(med([x[1] for x in g]), '$.2f'):>10s} "
              f"{f(med([x[2] for x in g]), ',.0f'):>11s} "
              f"{f(med([x[3] for x in g])):>13s} "
              f"{f(q(cg, .25)):>8s} {f(med(cg)):>9s} {f(q(cg, .75)):>8s}")


# ---------------------------------------------------------------- section D
def tradeable(c, limit=30):
    rows = list(c.execute(f"""SELECT name,class,variant,tournament,age_years,cagr,
                                     price_now,volume_30d,liquidity
                              FROM metrics
                              WHERE cagr IS NOT NULL AND class IN ('sticker','capsule')
                              ORDER BY cagr DESC LIMIT {limit}"""))
    print(f"  {'#':>3} {'name':40s} {'cls':7s} {'var':7s} {'age':>4s} {'CAGR':>8s} "
          f"{'price':>9s} {'vol30d':>9s} {'exit':>6s}")
    for i, r in enumerate(rows, 1):
        flag = "THIN" if (r[7] is not None and r[7] < THIN) else "ok"
        print(f"  {i:>3} {r[0][:40]:40s} {r[1][:7]:7s} {(r[2] or '-')[:7]:7s} "
              f"{(f'{r[4]:.1f}' if r[4] else '-'):>4s} {f(r[5]):>8s} "
              f"{f(r[6], '$.2f'):>9s} {f(r[7], ',.0f'):>9s} {flag:>6s}")
    n_thin = sum(1 for r in rows if r[7] is not None and r[7] < THIN)
    print(f"\n  {n_thin}/{len(rows)} of the top movers are below {THIN} units/30d "
          f"-- priced, but not exitable at that price.")


if __name__ == "__main__":
    c = db.connect()
    n = c.execute("SELECT COUNT(*) FROM metrics WHERE class='sticker'").fetchone()[0]
    print(f"=== 0. archive coverage per variant (the selection bias, measured) ===")
    coverage(c)
    print(f"\n=== A. variant vs appreciation (stickers with history: {n}) ===")
    by_variant(c)
    print("\n=== B. capsule vs the stickers of the same tournament ===")
    capsule_vs_stickers(c)
    print("\n=== C1. lifecycle, CAPSULES ===")
    lifecycle(c, "capsule")
    print("\n=== C2. lifecycle, STICKERS (computed separately, not inherited) ===")
    lifecycle(c, "sticker")
    print("\n=== D. top movers crossed with liquidity ===")
    tradeable(c)
    c.close()
