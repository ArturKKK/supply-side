# supply-side

Supply map for fixed-supply CS2 items (cases, sticker capsules, capsule stickers).
Question: **where is supply compressing while price has not repriced yet.**

Separate from `/opt/vulpes` in every way: own directory, own venv, own SQLite file
(`supply.db`), own systemd-free one-off scripts. Nothing here touches vulpes
services or databases.

## What Steam actually exposes (verified 2026-08-09, not assumed)

| endpoint | logged out | gives |
|---|---|---|
| `/market/appfilters/730` | works | the official facet tree: Type, Sticker Collection (121), Tournament (25), Collection (97) |
| `/market/search/render/` | works | `market_hash_name`, `sell_listings`, `sell_price`. **No volume, no history.** |
| `/market/priceoverview/` | works | `lowest_price`, `median_price`, `volume` (24h) |
| `/market/listings/730/<name>` | works, but | now a React SSR **app shell**. The legacy `var line1=[...]` daily-history array is **gone**. |
| `/market/pricehistory/` | **not used** | login-gated. Deliberately out of scope: a Steam session is account access, too high a price for public price data. Treated as closed, not worked around. |
| `/market/itemordershistogram` | n/a | not referenced by the current market bundles at all |

The listing-page `line1` route that the original plan was built on no longer
exists. That is a Steam-side change, not a scraping failure.

## Priority

`supply_trend` is the product, price history is a garnish.

1. inventory of all three classes with `sell_listings` — no login needed
2. **daily snapshot** (`snapshot.py`, cron 03:17) — builds our own listings
   history, since Steam publishes none
3. price/volume history only as a supplement, from public archives
   (`external_history.py`), never as the base

## Rate limiting

All market endpoints share one aggressive per-IP budget. A short burst earns a
multi-minute (observed: >10 min) 429 lockout across *all* of them at once.
`steamclient.py` therefore does one request per ~6 s with jitter, backs off
60/120/300/600/900 s on 429, and raises `SteamClosed` after six exhausted
ladders — at which point the run stops and reports. Nothing rotates, spoofs, or
otherwise works around the limit.

## Pipeline

```
./.venv/bin/python db.py                  # create schema
./.venv/bin/python step1_inventory.py     # containers + stickers per capsule facet
./.venv/bin/python status_load.py         # per-source drop-pool claims
./.venv/bin/python step2_fetch.py overview 200
./.venv/bin/python step2_fetch.py history 200   # needs steam_cookie.txt, else skipped
./.venv/bin/python metrics.py             # derived columns + supply_map.csv
./.venv/bin/python report.py              # counts + top-30
```

Every step is resumable; re-running continues from `run_meta` / existing rows.

## supply_trend

Defined as the change in `sell_listings` between an item's oldest and newest
snapshot. Steam publishes **no historical listing counts**, so this column is
NULL on a first run by construction — that run *is* t0. Re-running
`step1_inventory.py` later writes a second snapshot and the column fills in.
It is deliberately not back-filled with a proxy. `vol_trend_1y` (turnover) is
reported separately and is a different quantity.

## Metadata rules

* `source_capsule` comes from Steam's own Sticker Collection facet. Never guessed.
* `class` is derived from the item name; the rule that fired is stored in
  `items.class_basis`.
* `release_year` is the year of the earliest day in that item's price history —
  an observation, not a lookup. NULL without history.
* drop-pool `status` is loaded per source into `status_sources`
  (one row per item per source, see `data/status_claims.json`). When sources
  disagree the item is `disputed` and `status_detail` carries every verdict.
  Items no source names are `unknown`.
