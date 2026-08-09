"""Daily supply snapshot -- the project's own listings history.

Steam publishes no historical listing counts, so we build our own: one full walk
of every tracked facet per day, appending a fresh (name, ts, sell_listings) row.
After two runs supply_trend in metrics.py stops being NULL; after a few weeks it
is a real series, obtained without any login.

Container walk runs every day (cheap, ~11 pages). The sticker walk is heavy
(~240 pages) so it runs on WEEKLY_DAY only, unless --full is passed.
"""
import sys
import time

import db
import step1_inventory as inv
from steamclient import SteamClient, SteamClosed

WEEKLY_DAY = 6            # Sunday
STICKER_VOLUME_TOP = 200


def clear_progress(c, prefix):
    c.execute("DELETE FROM run_meta WHERE k LIKE ?", (prefix + "%",))
    c.commit()


def main():
    full = "--full" in sys.argv
    c = db.connect()
    cli = SteamClient(db.DB)
    t0 = time.time()
    print(f"=== snapshot {time.strftime('%Y-%m-%d %H:%M:%S')} full={full} ===", flush=True)

    try:
        clear_progress(c, "inv:containers")
        inv.walk(cli, c, "containers",
                 {"category_730_Type[]": "tag_CSGO_Type_WeaponCase"}, "inv:containers")

        if full or time.localtime().tm_wday == WEEKLY_DAY:
            facets = inv.load_facets()["730_StickerCapsule"]["tags"]
            clear_progress(c, "inv:cap:")
            for i, (tag, meta) in enumerate(facets.items(), 1):
                loc = meta.get("localized_name") or tag
                print(f"  [{i}/{len(facets)}] {loc}", flush=True)
                inv.walk(cli, c, loc,
                         {"category_730_Type[]": "tag_CSGO_Tool_Sticker",
                          "category_730_StickerCapsule[]": "tag_" + tag},
                         f"inv:cap:{tag}", force_class="sticker",
                         source_capsule=loc, source_tag=tag)
        else:
            print("  (sticker walk skipped -- weekly only)", flush=True)
    except SteamClosed as e:
        print(f"STOPPED: {e}", flush=True)
        c.close()
        sys.exit(3)

    n_snap = c.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    n_days = c.execute("SELECT COUNT(DISTINCT date(ts,'unixepoch')) FROM snapshots"
                       ).fetchone()[0]
    print(f"=== done in {(time.time() - t0) / 60:.1f} min | snapshot rows {n_snap} | "
          f"distinct days {n_days} | req {cli.n_req} | 429 {cli.n_429} ===", flush=True)
    c.close()


if __name__ == "__main__":
    main()
