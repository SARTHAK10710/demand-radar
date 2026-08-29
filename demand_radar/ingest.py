"""Ingest — pull demand-signal posts from real, live sources.

Live connectors (no scraping, official/public JSON APIs):
  * hn:            Hacker News comments + stories via the Algolia search API (open)
  * stackexchange: Stack Exchange questions via api.stackexchange.com (open)
  * reddit:        subreddit search via reddit's public JSON (works on a normal IP)

Source strings:
    hn:comments                 -> Hacker News, searched with the config's pain_keywords
    stackexchange:stackoverflow -> Stack Exchange site "stackoverflow"
    reddit:r/programming        -> subreddit "programming"

An optional seed_file (JSONL) can still be layered in for offline runs, but with
--live-ingest the tool runs on 100% genuine posts with clickable source URLs.
Any source that fails (rate limit, blocked IP, network) degrades silently so a
run always completes on whatever real data it could reach.
"""

from __future__ import annotations

import html as _html
import json
import os
import re
from typing import Callable, Iterable

from .config import Config
from .models import Post

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 demand-radar/0.1"
)

_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html(text: str | None) -> str:
    """Strip HTML tags and unescape entities from an API-returned body."""
    if not text:
        return ""
    return _html.unescape(_TAG_RE.sub(" ", text)).strip()


# --------------------------------------------------------------- seed file ---
def load_seed(path: str) -> list[Post]:
    posts: list[Post] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            raw = json.loads(line)
            posts.append(
                Post(
                    text=raw.get("text", ""),
                    source=raw.get("source", "seed"),
                    author=raw.get("author", "unknown"),
                    url=raw.get("url", ""),
                    title=raw.get("title", ""),
                    score=int(raw.get("score", 0)),
                    created_utc=raw.get("created_utc"),
                )
            )
    return posts


def _requests():
    try:
        import requests

        return requests
    except ImportError:
        return None


# --------------------------------------------------------------- Hacker News ---
def fetch_hackernews(
    queries: Iterable[str],
    limit: int = 80,
    logger: Callable[[str], None] = print,
) -> list[Post]:
    """Real HN comments + stories via the open Algolia search API (no auth)."""
    requests = _requests()
    if requests is None:
        logger("  [hn] `requests` not installed; skipping")
        return []

    queries = [q for q in queries if q] or ["*"]
    per = max(10, min(100, limit // len(queries)))
    posts: list[Post] = []
    for q in queries:
        try:
            resp = requests.get(
                "https://hn.algolia.com/api/v1/search",
                params={"query": q, "tags": "(comment,story)", "hitsPerPage": per},
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
        except Exception as e:
            logger(f"  [hn] query {q!r} failed ({e})")
            continue
        for h in hits:
            text = _clean_html(h.get("comment_text") or h.get("story_text") or "")
            title = h.get("story_title") or h.get("title") or ""
            if not text and not title:
                continue
            posts.append(
                Post(
                    text=text or title,
                    source="hn:comments",
                    author=h.get("author", "unknown"),
                    url=f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                    title=title,
                    score=int(h.get("points") or 0),
                    created_utc=h.get("created_at_i"),
                )
            )
    logger(f"  [hn] pulled {len(posts)} real posts across {len(queries)} queries")
    return posts


# ------------------------------------------------------------ Stack Exchange ---
def fetch_stackexchange(
    queries: Iterable[str],
    site: str = "stackoverflow",
    limit: int = 60,
    logger: Callable[[str], None] = print,
) -> list[Post]:
    """Real Stack Exchange questions via the open API (anonymous quota is fine)."""
    requests = _requests()
    if requests is None:
        logger("  [se] `requests` not installed; skipping")
        return []

    queries = [q for q in queries if q] or ["help"]
    per = max(5, min(50, limit // len(queries)))
    posts: list[Post] = []
    for q in queries:
        try:
            resp = requests.get(
                "https://api.stackexchange.com/2.3/search/advanced",
                params={
                    "order": "desc",
                    "sort": "relevance",
                    "q": q,
                    "site": site,
                    "pagesize": per,
                    "filter": "withbody",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
        except Exception as e:
            logger(f"  [se:{site}] query {q!r} failed ({e})")
            continue
        for it in items:
            title = _clean_html(it.get("title", ""))
            body = _clean_html(it.get("body", ""))[:800]
            if not title:
                continue
            posts.append(
                Post(
                    text=(f"{title}. {body}").strip(),
                    source=f"stackexchange:{site}",
                    author=(it.get("owner") or {}).get("display_name", "unknown"),
                    url=it.get("link", ""),
                    title=title,
                    score=int(it.get("score") or 0),
                    created_utc=it.get("creation_date"),
                )
            )
    logger(f"  [se:{site}] pulled {len(posts)} real questions across {len(queries)} queries")
    return posts


# -------------------------------------------------------------------- Reddit ---
def fetch_reddit(
    subreddit: str,
    keywords: Iterable[str],
    limit: int = 80,
    logger: Callable[[str], None] = print,
) -> list[Post]:
    """Real subreddit search via reddit's public JSON.

    Reddit blocks data-center IPs (you'll see 403 here in the sandbox) but this
    works from a normal residential connection. It fails soft either way.
    """
    requests = _requests()
    if requests is None:
        logger(f"  [reddit] `requests` not installed; skipping r/{subreddit}")
        return []

    query = " OR ".join(f'"{k}"' for k in keywords) if keywords else ""
    try:
        resp = requests.get(
            f"https://www.reddit.com/r/{subreddit}/search.json",
            params={"q": query, "restrict_sr": 1, "limit": min(limit, 100),
                    "sort": "new", "t": "year"},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        children = resp.json().get("data", {}).get("children", [])
    except Exception as e:
        logger(f"  [reddit] r/{subreddit} unavailable ({e}) — likely IP-blocked here; "
               f"works on a residential connection")
        return []

    posts: list[Post] = []
    for child in children:
        d = child.get("data", {})
        posts.append(
            Post(
                text=_clean_html(d.get("selftext", "")) or d.get("title", ""),
                source=f"reddit:r/{subreddit}",
                author=d.get("author", "unknown"),
                url="https://www.reddit.com" + d.get("permalink", ""),
                title=d.get("title", ""),
                score=int(d.get("score", 0)),
                created_utc=d.get("created_utc"),
            )
        )
    logger(f"  [reddit] r/{subreddit}: pulled {len(posts)} real posts")
    return posts


# ---------------------------------------------------------------- dispatch ---
def _fetch_source(src: str, config: Config, logger: Callable[[str], None]) -> list[Post]:
    lim = config.max_posts_per_source
    if src.startswith(("hn:", "hackernews:")):
        return fetch_hackernews(config.pain_keywords, limit=lim, logger=logger)
    if src.startswith(("stackexchange:", "se:", "stackoverflow:")):
        site = src.split(":", 1)[1].strip() or "stackoverflow"
        if site in ("comments", "search", ""):
            site = "stackoverflow"
        return fetch_stackexchange(config.pain_keywords, site=site, limit=lim, logger=logger)
    if src.startswith("reddit:"):
        sub = src.split(":", 1)[1].strip().removeprefix("r/")
        return fetch_reddit(sub, config.pain_keywords, limit=lim, logger=logger)
    logger(f"  [{src}] no live connector; using seed-provided posts if any")
    return []


def ingest(
    config: Config,
    live: bool = False,
    logger: Callable[[str], None] = print,
) -> list[Post]:
    """Assemble the post set for a run: optional seed file + optional live sources."""
    posts: list[Post] = []

    if config.seed_file and os.path.exists(config.seed_file):
        seed_posts = load_seed(config.seed_file)
        logger(f"  [seed] loaded {len(seed_posts)} posts from {config.seed_file}")
        posts.extend(seed_posts)
    elif config.seed_file:
        logger(f"  [seed] file not found: {config.seed_file}")

    if live:
        for src in config.sources:
            posts.extend(_fetch_source(src, config, logger))

    if not posts:
        logger("  [ingest] no posts ingested — set a seed_file or pass --live-ingest "
               "with reachable sources")

    # De-duplicate by content id, keeping the first occurrence.
    seen: set[str] = set()
    unique: list[Post] = []
    for p in posts:
        if not p.full_text.strip() or p.id in seen:
            continue
        seen.add(p.id)
        unique.append(p)

    logger(f"  [ingest] {len(unique)} unique posts ready for classification")
    return unique
