"""Polite, resumable HTTP client for the Steam Community Market.

Rules of engagement (project-level, deliberate):
  * one request per PACE seconds, plus jitter -- never bursts;
  * 429 -> exponential backoff with a hard ceiling, request is retried;
  * MAX_CONSECUTIVE_429 backoffs in a row -> raise SteamClosed and stop the run.
    We do not rotate anything, do not spoof anything, do not work around limits.
"""
import json
import random
import sqlite3
import time

import requests

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36")

PACE = 6.0                 # seconds between requests
JITTER = 1.5
BACKOFF = [60, 120, 300, 600, 900, 900]   # on 429 / 5xx
MAX_CONSECUTIVE_429 = 6    # after this many exhausted backoffs -> give up


class SteamClosed(RuntimeError):
    """Steam kept refusing after the full backoff ladder."""


class SteamClient:
    def __init__(self, db_path=None):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": UA,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/json,*/*",
        })
        self._last = 0.0
        self.db_path = db_path
        self.n_req = 0
        self.n_429 = 0
        self.consecutive_429 = 0

    # -- pacing ---------------------------------------------------------
    def _wait(self):
        dt = time.time() - self._last
        need = PACE + random.uniform(0, JITTER) - dt
        if need > 0:
            time.sleep(need)
        self._last = time.time()

    def _log(self, url, status, nbytes, note=""):
        if not self.db_path:
            return
        try:
            c = sqlite3.connect(self.db_path, timeout=30)
            c.execute("INSERT INTO fetch_log(ts,url,status,bytes,note) VALUES(?,?,?,?,?)",
                      (int(time.time()), url[:300], status, nbytes, note))
            c.commit()
            c.close()
        except Exception:
            pass

    # -- core -----------------------------------------------------------
    def get(self, url, params=None, expect_json=False):
        """Return (status_code, text_or_json). Retries 429/5xx, raises SteamClosed."""
        attempt = 0
        while True:
            self._wait()
            try:
                r = self.s.get(url, params=params, timeout=45)
            except requests.RequestException as e:
                if attempt >= len(BACKOFF) - 1:
                    self._log(url, -1, 0, type(e).__name__)
                    return -1, None
                w = BACKOFF[attempt]
                print(f"      net {type(e).__name__}; sleep {w}s", flush=True)
                time.sleep(w)
                attempt += 1
                continue

            self.n_req += 1
            code = r.status_code

            if code == 200:
                self.consecutive_429 = 0
                self._log(url, 200, len(r.content))
                if expect_json:
                    try:
                        return 200, r.json()
                    except json.JSONDecodeError:
                        self._log(url, 200, len(r.content), "bad-json")
                        return 200, None
                return 200, r.text

            if code in (429, 500, 502, 503, 504):
                if code == 429:
                    self.n_429 += 1
                self._log(url, code, 0)
                if attempt >= len(BACKOFF) - 1:
                    self.consecutive_429 += 1
                    if self.consecutive_429 >= MAX_CONSECUTIVE_429:
                        raise SteamClosed(
                            f"{self.consecutive_429} exhausted backoff ladders in a row "
                            f"(last HTTP {code}). Stopping as instructed.")
                    return code, None
                w = BACKOFF[attempt]
                print(f"      HTTP {code}; backoff {w}s "
                      f"(req={self.n_req}, 429s={self.n_429})", flush=True)
                time.sleep(w)
                attempt += 1
                continue

            # 404 / 302 / etc -- caller's problem, no retry
            self._log(url, code, len(r.content))
            return code, None


SEARCH_URL = "https://steamcommunity.com/market/search/render/"
LISTING_URL = "https://steamcommunity.com/market/listings/730/"


def search_page(cli, start, count=100, extra=None, sort=None):
    """One page of /market/search/render/. Returns dict or None."""
    p = {"appid": 730, "norender": 1, "start": start, "count": count,
         "currency": 1, "country": "US", "language": "english"}
    if sort:
        p["sort_column"], p["sort_dir"] = sort
    if extra:
        p.update(extra)
    code, j = cli.get(SEARCH_URL, params=p, expect_json=True)
    if code == 200 and isinstance(j, dict) and j.get("success"):
        return j
    return None
