"""Sticker taxonomy from the market_hash_name, and target selection.

Market names are structured: `Sticker | <subject> (<variant>) | <tournament>`.
Everything below is parsed out of that string -- nothing is inferred from
outside knowledge. Names without a tournament segment, or in a language other
than English, are dropped rather than guessed at.

Capsules and individual stickers are deliberately kept as separate classes: a
capsule is a lottery ticket over a set, a sticker is one specific item, and
their supply mechanics differ (capsules are only destroyed, stickers are both
created by opening capsules and destroyed by being applied to a weapon).
"""
import html
import re
from collections import defaultdict

import db

VARIANTS = ("Holo", "Gold", "Foil", "Glitter", "Lenticular")
# tournaments named in the brief, plus the rest we can parse, with the year the
# tournament ran -- taken from the name itself, not from any external table
TOUR_RE = re.compile(r"^(?:(?P<pre>\d{4})\s+)?(?P<name>.+?)\s*(?P<post>\d{4})?$")

OLD_MAJORS = ["Krakow 2017", "Boston 2018", "Atlanta 2017", "Katowice 2019",
              "London 2018", "Berlin 2019", "Cologne 2016", "MLG Columbus 2016"]
NEW_MAJORS = ["Paris 2023", "Copenhagen 2024", "Shanghai 2024", "Austin 2025",
              "Budapest 2025"]
MID_MAJORS = ["Stockholm 2021", "Antwerp 2022", "Rio 2022"]


def parse(name):
    """-> dict or None. Only English, tournament-tagged stickers survive."""
    n = html.unescape(name).strip()
    if not n.startswith("Sticker |"):
        return None
    parts = [p.strip() for p in n.split("|")]
    if len(parts) < 3:
        return None
    subject, tour = parts[1], parts[-1]
    if re.search(r"[А-Яа-яÁ-Úá-ú]", tour):        # localized archive URLs
        return None
    m = re.search(r"\((" + "|".join(VARIANTS) + r")\)\s*$", subject)
    variant = m.group(1) if m else "Paper"
    subject = re.sub(r"\s*\((" + "|".join(VARIANTS) + r")\)\s*$", "", subject).strip()
    ym = re.search(r"(19|20)\d{2}", tour)
    if not ym:
        return None
    return dict(name=n, subject=subject, variant=variant, tournament=tour,
                year=int(ym.group(0)))


def all_stickers(c):
    out = []
    for (n,) in c.execute("SELECT name FROM archive_names WHERE name LIKE 'Sticker |%'"):
        p = parse(n)
        if p:
            out.append(p)
    return out


def select_targets(c, n_old=8, n_other=3):
    """Balanced design: for each tournament of interest, take the subjects that
    exist in the most variants, and take *all* their variants. That is what makes
    a Paper-vs-Holo-vs-Gold comparison meaningful instead of anecdotal.

    Old majors get more subjects than recent ones -- they are the ones whose
    distribution closed long ago, which is the question being asked. Turnover
    would be the better selector, but turnover is only knowable after the
    history is fetched, so it cannot drive the fetch."""
    rows = all_stickers(c)
    by_tour = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_tour[r["tournament"]][r["subject"]].append(r)
    targets = []
    for tour in OLD_MAJORS + NEW_MAJORS + MID_MAJORS:
        subs = by_tour.get(tour, {})
        k = n_old if tour in OLD_MAJORS else n_other
        ranked = sorted(subs.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        for subject, items in ranked[:k]:
            targets.extend(items)
    return targets


if __name__ == "__main__":
    c = db.connect()
    rows = all_stickers(c)
    print(f"parsed stickers: {len(rows)}")
    from collections import Counter
    print("\nby variant:")
    for k, v in Counter(r["variant"] for r in rows).most_common():
        print(f"  {k:12s} {v}")
    print("\nby tournament (top 20):")
    for k, v in Counter(r["tournament"] for r in rows).most_common(20):
        print(f"  {k:20s} {v}")
    t = select_targets(c)
    print(f"\nselected targets: {len(t)}")
    print("  variants in selection:",
          dict(Counter(r["variant"] for r in t)))
    with open("/root/projects/supply-side/data/sticker_targets.txt", "w") as f:
        f.write("\n".join(r["name"] for r in t))
    print("  -> data/sticker_targets.txt")
    c.close()
