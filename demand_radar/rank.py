"""Rank — score each candidate segment and pick the beachhead to attack first.

Composite score blends three factors, each normalised to 0-1:
  * volume       — how much demand exists (size of the cluster)
  * intent       — how ready-to-buy that demand is (browsing < looking < paying)
  * competition  — how crowded the space looks (inverted: emptier scores higher)

Weights are configurable. The top-scoring segment is the recommended beachhead:
the smallest winnable market with the strongest, least-contested demand.
"""

from __future__ import annotations

from .config import Config
from .models import Segment


def _competition(seg: Segment, config: Config) -> float:
    """Rough 0-1 crowdedness estimate (higher = more contested).

    Priority: an explicit per-segment override in the config, else a proxy from
    how often posts already name incumbent tools (more mentions = more crowded).
    Defaults to 0.5 when there's nothing to go on — honestly rough, by design.
    """
    if seg.name in config.competition_override:
        return max(0.0, min(1.0, float(config.competition_override[seg.name])))

    if config.competitor_keywords:
        mentions = 0
        for p in seg.posts:
            low = p.post.full_text.lower()
            if any(kw.lower() in low for kw in config.competitor_keywords):
                mentions += 1
        return round(mentions / max(1, seg.volume), 3)

    return 0.5


def rank(segments: list[Segment], config: Config) -> list[Segment]:
    """Populate scores + ranks on the segments and return them sorted best-first."""
    if not segments:
        return []

    max_volume = max(s.volume for s in segments) or 1
    w = config.rank_weights
    weight_sum = (w.volume + w.intent + w.competition) or 1.0

    for seg in segments:
        seg.volume_score = round(seg.volume / max_volume, 3)

        # Average intent weight (1..3) mapped to 0..1.
        if seg.posts:
            avg_intent = sum(p.intent_weight for p in seg.posts) / len(seg.posts)
        else:
            avg_intent = 1.0
        seg.intent_score = round((avg_intent - 1.0) / 2.0, 3)

        seg.competition = _competition(seg, config)
        seg.competition_score = round(1.0 - seg.competition, 3)

        seg.total_score = round(
            (
                w.volume * seg.volume_score
                + w.intent * seg.intent_score
                + w.competition * seg.competition_score
            )
            / weight_sum,
            3,
        )

    segments.sort(key=lambda s: s.total_score, reverse=True)
    for i, seg in enumerate(segments, start=1):
        seg.rank = i
    return segments


def beachhead(segments: list[Segment]) -> Segment | None:
    return segments[0] if segments else None
