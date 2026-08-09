"""SQLite schema. Everything derived is kept separate from everything observed."""
import sqlite3

DB = "/root/projects/supply-side/supply.db"

SCHEMA = """
PRAGMA journal_mode=WAL;

-- observed: one row per market item found during inventory
CREATE TABLE IF NOT EXISTS items (
    name              TEXT PRIMARY KEY,       -- market_hash_name
    class             TEXT,                   -- case | capsule | sticker | container_other
    class_basis       TEXT,                   -- how class was decided
    source_capsule    TEXT,                   -- Steam StickerCapsule facet localized name, or NULL
    source_tag        TEXT,                   -- the raw facet tag
    tournament        TEXT,                   -- Steam Tournament facet, or NULL
    steam_type        TEXT,                   -- asset_description.type verbatim
    first_seen        INTEGER
);

-- observed: point-in-time market state. Repeat runs make supply_trend real.
CREATE TABLE IF NOT EXISTS snapshots (
    name          TEXT,
    ts            INTEGER,
    sell_listings INTEGER,                     -- THE supply reading
    price_usd     REAL,                        -- lowest listed price
    median_usd    REAL,                        -- priceoverview median
    volume_24h    INTEGER,                     -- priceoverview 24h units
    PRIMARY KEY (name, ts)
);

-- observed: daily sales from the listing page's line1 array
CREATE TABLE IF NOT EXISTS history (
    name      TEXT,
    day       TEXT,                            -- YYYY-MM-DD
    price_usd REAL,                            -- volume-weighted price that day
    volume    INTEGER,                         -- units sold that day
    source    TEXT DEFAULT 'wayback',          -- never Steam: see README
    PRIMARY KEY (name, day)
);

CREATE TABLE IF NOT EXISTS history_meta (
    name          TEXT PRIMARY KEY,
    item_nameid   TEXT,
    n_points      INTEGER,
    first_day     TEXT,
    last_day      TEXT,
    fetched_ts    INTEGER,
    http_status   INTEGER
);

-- observed: what each external source says about drop-pool status. One row per
-- (item, source). Disagreements are preserved, never collapsed.
CREATE TABLE IF NOT EXISTS status_sources (
    name    TEXT,
    source  TEXT,
    status  TEXT,
    note    TEXT,
    ts      INTEGER,
    PRIMARY KEY (name, source)
);

CREATE TABLE IF NOT EXISTS fetch_log (
    ts INTEGER, url TEXT, status INTEGER, bytes INTEGER, note TEXT
);

CREATE TABLE IF NOT EXISTS run_meta (k TEXT PRIMARY KEY, v TEXT);

-- derived: the product. Rebuilt from scratch by metrics.py.
CREATE TABLE IF NOT EXISTS metrics (
    name            TEXT PRIMARY KEY,
    class           TEXT,
    source_capsule  TEXT,
    release_year    INTEGER,
    status          TEXT,
    status_detail   TEXT,
    price_now       REAL,
    listings_now    INTEGER,
    volume_30d      INTEGER,
    price_1y        REAL,
    price_2y        REAL,
    price_3y        REAL,
    cagr_1y         REAL,
    cagr_2y         REAL,
    cagr_3y         REAL,
    cagr            REAL,
    supply_trend    REAL,
    supply_basis    TEXT,
    months_supply   REAL,
    vol_trend_1y    REAL,
    baseline_cagr   REAL,      -- what the legacy fixed-supply cohort did
    excess_cagr     REAL,      -- this item minus that cohort. negative = lagging
    lag_score       REAL,
    confidence      TEXT
);

CREATE INDEX IF NOT EXISTS ix_hist_name ON history(name);
CREATE INDEX IF NOT EXISTS ix_snap_name ON snapshots(name);
"""


def connect():
    c = sqlite3.connect(DB, timeout=60)
    c.executescript(SCHEMA)
    return c


if __name__ == "__main__":
    c = connect()
    print("db:", DB)
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1"):
        n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:16s} {n}")
    c.close()
