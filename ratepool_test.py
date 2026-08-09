"""Mechanical test of the "rare case drop pool was disabled in January 2026" claim.

The claim is not in any Valve communication (see primary_sources.py), so it is
tested against numbers instead of against websites.

Design -- difference-in-differences on daily Steam sales data:

  group A  cases every source agrees stopped being handed out long ago and
           would be the ones affected if a legacy pool were switched off
  group B  cases every source agrees were still in the active weekly pool
           across the whole window

  pre  window   [break-75d, break-10d]
  post window   [break+7d,  break+40d]

  For each case: dlogP = log(median post price / median pre price)
                 dlogV = log(mean post daily units / mean pre daily units)
  DiD = mean(A) - mean(B).

If legacy supply really stopped, A should reprice up relative to B (positive
DiD on price) and A's units traded should fall relative to B. If both groups
move together, whatever happened in January was market-wide, not a supply cut
aimed at legacy cases.

Small n and a short post window: this can falsify a large effect, it cannot
prove a small one. That limitation is printed with the result, not hidden.
"""
import math
import statistics as st
import sys
import time

import db

GROUP_A = ["Operation Bravo Case", "CS:GO Weapon Case", "Huntsman Weapon Case",
           "Chroma Case", "Falchion Case", "Shadow Case", "Glove Case",
           "Spectrum Case", "Clutch Case", "Danger Zone Case", "Horizon Case",
           "Prisma Case", "CS20 Case", "Gamma Case"]
GROUP_B = ["Kilowatt Case", "Revolution Case", "Dreams & Nightmares Case"]
# group C -- fixed supply like A, but never in any drop pool at any point, so a
# drop-pool change cannot touch them. If C moves with A, whatever happened in
# January was not about the drop pool.
GROUP_C = ["Cologne 2016 Legends (Holo/Foil)", "Atlanta 2017 Legends (Holo/Foil)",
           "Boston 2018 Legends (Holo/Foil)", "Katowice 2019 Legends (Holo/Foil)",
           "Berlin 2019 Legends (Holo/Foil)",
           "Stockholm 2021 Legends Sticker Capsule",
           "Antwerp 2022 Legends Sticker Capsule",
           "Rio 2022 Legends Sticker Capsule",
           "Paris 2023 Legends Sticker Capsule",
           "Copenhagen 2024 Legends Sticker Capsule",
           "Community Sticker Capsule 1", "Sticker Capsule 2"]


def to_day(s):
    return time.mktime(time.strptime(s, "%Y-%m-%d")) / 86400.0


def series(c, name):
    return [(to_day(d), p, v) for d, p, v in c.execute(
        "SELECT day,price_usd,volume FROM history WHERE name=? ORDER BY day", (name,))]


def window(rows, lo, hi):
    return [(p, v) for d, p, v in rows if lo <= d <= hi]


def stats(rows, brk, pre=(-75, -10), post=(7, 40)):
    b = to_day(brk)
    a = window(rows, b + pre[0], b + pre[1])
    z = window(rows, b + post[0], b + post[1])
    if len(a) < 15 or len(z) < 10:
        return None
    p0 = st.median([p for p, _ in a if p])
    p1 = st.median([p for p, _ in z if p])
    v0 = st.mean([v for _, v in a])
    v1 = st.mean([v for _, v in z])
    if not (p0 and p1):
        return None
    return (math.log(p1 / p0), math.log(v1 / v0) if v0 and v1 else None,
            p0, p1, v0, v1, len(a), len(z))


def run(c, brk):
    print("=" * 98)
    print(f"BREAK DATE TESTED: {brk}")
    print("=" * 98)
    out = {}
    for grp, names in (("A_legacy", GROUP_A), ("B_active", GROUP_B),
                       ("C_capsules", GROUP_C)):
        print(f"\n{grp}")
        print(f"  {'case':32s} {'pre$':>8s} {'post$':>8s} {'dlogP':>7s} "
              f"{'preVol':>8s} {'postVol':>8s} {'dlogV':>7s}")
        vals = []
        for n in names:
            rows = series(c, n)
            if not rows:
                print(f"  {n:32s} {'no history':>8s}")
                continue
            s = stats(rows, brk)
            if s is None:
                last = time.strftime('%Y-%m-%d', time.gmtime(max(d for d, _, _ in rows) * 86400))
                print(f"  {n:32s} insufficient window (history ends {last})")
                continue
            dP, dV, p0, p1, v0, v1, na, nz = s
            vals.append((dP, dV))
            print(f"  {n:32s} {p0:8.2f} {p1:8.2f} {dP:+7.3f} "
                  f"{v0:8.0f} {v1:8.0f} {(f'{dV:+7.3f}' if dV is not None else '      -')}")
        out[grp] = vals
    a = out.get("A_legacy", [])
    if not a:
        print("\n  cannot compute: group A has no usable series")
        return
    print("\n" + "-" * 98)

    def m(vals, idx):
        v = [x[idx] for x in vals if x[idx] is not None]
        return st.mean(v) if v else None

    for label, grp in (("B_active", out.get("B_active", [])),
                       ("C_capsules", out.get("C_capsules", []))):
        if not grp:
            print(f"  vs {label}: no usable series")
            continue
        for what, idx in (("price ", 0), ("volume", 1)):
            am, gm = m(a, idx), m(grp, idx)
            if am is None or gm is None:
                continue
            print(f"  {what} A - {label:11s} A={am:+.3f} ({math.exp(am) - 1:+.1%})  "
                  f"{label[0]}={gm:+.3f} ({math.exp(gm) - 1:+.1%})  "
                  f"DiD={am - gm:+.3f} ({math.exp(am - gm) - 1:+.1%})")
        print(f"    n_A={len(a)}  n_{label[0]}={len(grp)}")


if __name__ == "__main__":
    c = db.connect()
    for brk in (sys.argv[1:] or ["2026-01-09", "2026-01-21"]):
        run(c, brk)
        print()
    c.close()
