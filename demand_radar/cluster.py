"""Cluster + size — group tagged posts into segments and roll up their shape.

This is the step that turns a pile of labelled posts into an *empirically sized*
set of candidate ICPs: one Segment per distinct label, with volume counts and
human-readable summaries of the use cases, pains, and intent mix inside each.
"""

from __future__ import annotations

from collections import Counter

from .models import ClassifiedPost, Segment


def _top_n(counter: Counter, n: int = 5) -> list[tuple[str, int]]:
    return [(k, v) for k, v in counter.most_common(n) if k]


def cluster(classified: list[ClassifiedPost]) -> list[Segment]:
    """Group relevant classified posts into sized Segments."""
    buckets: dict[str, list[ClassifiedPost]] = {}
    for cp in classified:
        if not cp.is_relevant:
            continue
        buckets.setdefault(cp.segment, []).append(cp)

    segments: list[Segment] = []
    for name, posts in buckets.items():
        seg = Segment(name=name, posts=posts, volume=len(posts))
        seg.top_use_cases = _top_n(Counter(p.use_case for p in posts))
        seg.top_pains = _top_n(Counter(p.pain for p in posts))
        seg.intent_breakdown = {
            level: sum(1 for p in posts if p.intent == level)
            for level in ("browsing", "looking", "paying")
        }
        segments.append(seg)

    # Sort by raw volume for now; ranking assigns the real ordering next.
    segments.sort(key=lambda s: s.volume, reverse=True)
    return segments
