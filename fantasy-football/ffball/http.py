"""Tiny dependency-free HTTP + JSON cache helper.

Uses only the standard library so the data layer installs nothing. Big/slow
payloads (notably Sleeper's full players list) are cached to disk with a TTL so
normal use stays well under Sleeper's rate limits.
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Optional

DEFAULT_CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"
USER_AGENT = "ffball/0.1 (+https://github.com/unite-ideas/one)"


class HttpError(RuntimeError):
    """Raised when a request fails (network, non-200, or blocked proxy)."""


def get_json(url: str, timeout: int = 30) -> Any:
    """GET a URL and parse JSON. Raises HttpError on any failure."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:  # pragma: no cover - network dependent
        raise HttpError(f"HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network dependent
        raise HttpError(
            f"Could not reach {url}: {exc.reason}. "
            "If you are in a restricted sandbox this host may be blocked; "
            "run on an environment with open network."
        ) from exc
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def get_json_cached(
    url: str,
    cache_key: str,
    ttl_seconds: int = 86_400,
    cache_dir: Optional[Path] = None,
    timeout: int = 60,
) -> Any:
    """GET JSON with a disk cache.

    Returns cached data if it is younger than ``ttl_seconds``. On a network
    failure but with a *stale* cache present, returns the stale cache rather
    than blowing up (better an old players list than none).
    """
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{cache_key}.json"

    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < ttl_seconds:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)

    try:
        data = get_json(url, timeout=timeout)
    except HttpError:
        if path.exists():  # fall back to stale cache
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        raise

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return data
