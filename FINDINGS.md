# Findings

Everything below is reproducible from the scripts in this repo. Dates are the
dates the check was run, not the date the underlying page was written.

---

## 1. Steam removed the daily price history from listing pages

Checked 2026-08-09. `/market/listings/730/<name>` is now a React SSR app shell:
228 KB of HTML with zero occurrences of `line1`, `item_nameid`, `g_rgListingInfo`,
or any item data. The bundles under `/steamcommunity/public/ssr/` load history
through an RSC server action, not a public JSON route.

Consequences:

* the plan's "read `line1` off the listing page" route is dead, Steam-side
* `/market/priceoverview/` still answers logged-out clients and is what the
  current UI itself calls — this is where 24h volume comes from
* `/market/pricehistory/` is login-gated and is **not used by this project**:
  a Steam session is account access, and that is too high a price for public
  price data. Not a workaround target.

## 2. Rate limiting

All market endpoints share one per-IP budget. A short burst of ~25 requests
earned a 429 lockout across *every* market endpoint simultaneously, lasting
over 20 minutes. Probing during the lockout appears to extend it, so the
collector waits in silence (15 min between probes) rather than polling.

## 3. Valve has never announced removing cases from the drop pool

Primary source: `ISteamNews` feed for appid 730 — 500 posts, 2022-03-02 to
2026-08-03, stored at `data/valve_cs2_news.json`. Full-text search for
`rare`, `drop pool`, `no longer drop`, `removed <case|container>`:

* **no post announces cases being removed from drops**
* **the phrase "rare drop pool" never appears**

The only January 2026 drop-list change in Valve's own words (2026-01-21):

> Added two all-new weapon collections to the Weekly Care Package drop list:
> Harlequin, Achroma. Removed four weapon collections from the Weekly Care
> Package drop list: Safehouse, Dust 2, 2018 Nuke Collection, and the 2018
> Inferno Collection

Those are **weapon-skin collections, not cases**. The widely-repeated claim that
the *rare case pool* was disabled on 2026-01-08/09 is not in this feed, and its
date does not match the one real January change (2026-01-21).

## 4. Mechanical test of the rare-pool claim

Rather than counting websites, the claim was tested against daily sales data
recovered from pre-rewrite Internet Archive captures of Steam listing pages
(`external_history.py`; 12 legacy cases with 2,371-4,534 daily observations each,
running to 2026-02..2026-05).

Difference-in-differences, `ratepool_test.py`:

* group A — 12 cases every source agrees are long out of the active pool
* group B — cases every source agrees were still actively dropping
  (Kilowatt, Revolution, Dreams & Nightmares — only three exist, which caps the
  control group)
* pre `[break-75d, break-10d]`, post `[break+7d, break+40d]`

n_A = 14, n_B = 3.

| break tested | DiD price | DiD volume | usable as placebo |
|---|---|---|---|
| 2025-06-01 | +17.8% | -14.1% | yes |
| 2025-08-01 | +16.6% | -8.3% | yes |
| 2025-10-01 | -12.5% | +22.7% | yes |
| 2025-11-15 | **+27.2%** | +2.8% | yes |
| 2026-01-09 (rumour date) | +26.7% | **-36.3%** | — test |
| 2026-01-21 (Valve's real change) | +28.6% | -35.8% | — test |
| 2026-03-01 | -7.7% | -28.3% | **no** — its pre-window (Dec 16-Feb 19) contains January, so it re-measures the same event |

**Price: the January effect is not special.** A positive price DiD for legacy
over active cases appears at most break dates, and 2025-11-15 (+27.2%) matches
January (+26.7%). This is the ordinary behaviour of a fixed-supply asset against
a still-inflating one. The "+20-40% because the rare pool was removed" claim is
indistinguishable from that baseline drift.

**Volume: January is outside the placebo range.** Across the four clean placebo
dates the volume DiD spans -14.1% to +22.7%. January is -36.3%, clearly below
that band. Legacy case turnover fell hard relative to still-dropping cases.

**But the two halves do not fit the story.** A genuine supply cut should show up
as quantity down *and* price up more than usual. Here quantity collapses while
the price response stays within its normal range.

### Seasonality: the same test on previous Januaries

The pre-window always contains December, when the Steam sale lifts turnover, so
the January volume drop had to be checked against other Januaries.

| break | DiD price | DiD volume | drop-pool event claimed? |
|---|---|---|---|
| 2024-01-09 | **+58.8%** | **-30.2%** | no |
| 2025-01-09 | +5.7% | -2.4% | no |
| 2026-01-09 | +26.7% | -36.3% | yes (the rumour) |

January 2024 reproduces the January 2026 pattern — a larger price DiD and a
comparable volume DiD — in a year when nobody claims anything happened to the
drop pool. January 2025 shows neither. So the effect recurs without the alleged
cause, and is absent in a year that had the same alleged non-cause.

### Control group C: items a drop-pool change cannot touch

Major sticker capsules are fixed supply and were never in any drop pool, so a
change to the pool cannot reach them. Same window, break 2026-01-09:

| group | price | volume |
|---|---|---|
| A — legacy cases (n=14) | +15.3% | **-34.3%** |
| B — active-pool cases (n=3) | -9.0% | +3.0% |
| C — major capsules (n=3) | +10.1% | **-47.5%** |

DiD A-C: price +4.8%, volume **+25.0%** — legacy cases fell *less* than the
items that cannot be affected at all. The January turnover collapse is
market-wide across fixed-supply CS2 collectibles.

**Verdict: contradicted, not merely unconfirmed.** Four independent checks:

1. no primary source — Valve has never said it, in 500 posts
2. the price effect is inside the placebo range (Nov 2025 is larger)
3. the volume effect reproduces in January 2024, a year with no such event
4. the volume effect is *stronger* in items a drop-pool change cannot reach

The status stays `UNCONFIRMED_RUMOR` in `data/status_claims.json` and no
conclusion is derived from it. n_B and n_C are 3 each, which is the ceiling —
only three cases are undisputedly still dropping — so each single check is weak;
the four together point the same way.

Limits, stated rather than buried: the control group cannot exceed 3 items,
because only 3 cases are undisputedly still dropping; adjacent break dates share
windows, so placebo estimates are not independent of each other; and a
difference in differences locates a break, never a mechanism.

## 5. What this means for the 16 disputed items

The disagreements (Fever / Recoil / Fracture "active vs discontinued", and 12
cases "rare_pool vs discontinued") are all downstream of the same unresolved
question. They stay `disputed` until it is settled by our own listings series.
