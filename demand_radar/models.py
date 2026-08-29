"""Core data structures that flow through the Demand Radar pipeline.

Everything is a plain dataclass so the stages stay easy to test, serialise to
JSON, and reason about. Posts are ingested, then classified, then clustered into
segments, then the winning segment's posts become scored leads.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional

# The three intent levels, ordered weakest -> strongest buying signal.
INTENT_LEVELS = ("browsing", "looking", "paying")
INTENT_WEIGHT = {"browsing": 1.0, "looking": 2.0, "paying": 3.0}


@dataclass
class Post:
    """A single raw demand signal pulled from a source."""

    text: str
    source: str                      # e.g. "reddit:r/NewTubers", "upwork:video editing"
    author: str = "unknown"
    url: str = ""
    title: str = ""
    score: int = 0                   # upvotes / engagement, if the source provides it
    created_utc: Optional[float] = None

    @property
    def id(self) -> str:
        """Stable id derived from content, so re-runs de-duplicate cleanly."""
        h = hashlib.sha1(f"{self.source}|{self.title}|{self.text}".encode("utf-8"))
        return h.hexdigest()[:12]

    @property
    def full_text(self) -> str:
        return f"{self.title}\n{self.text}".strip()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d


@dataclass
class ClassifiedPost:
    """A post after the LLM (or heuristic) classifier has tagged it."""

    post: Post
    segment: str                     # normalised segment slug, or "none" if irrelevant
    use_case: str
    pain: str
    intent: str                      # one of INTENT_LEVELS
    confidence: float = 0.5          # 0-1, how sure the classifier is
    method: str = "llm"              # "llm" or "heuristic" — provenance for honesty

    @property
    def intent_weight(self) -> float:
        return INTENT_WEIGHT.get(self.intent, 1.0)

    @property
    def is_relevant(self) -> bool:
        return self.segment not in ("none", "", None)

    def to_dict(self) -> dict:
        return {
            "post": self.post.to_dict(),
            "segment": self.segment,
            "use_case": self.use_case,
            "pain": self.pain,
            "intent": self.intent,
            "confidence": self.confidence,
            "method": self.method,
        }


@dataclass
class Segment:
    """A candidate ICP: a cluster of classified posts, sized and scored."""

    name: str
    posts: list[ClassifiedPost] = field(default_factory=list)

    # Populated during ranking.
    volume: int = 0
    volume_score: float = 0.0        # 0-1 normalised
    intent_score: float = 0.0        # 0-1 normalised
    competition: float = 0.5         # 0-1, higher = more crowded (worse)
    competition_score: float = 0.0   # 0-1, already inverted so higher = better
    total_score: float = 0.0         # 0-1 composite
    rank: int = 0

    # Human-readable rollups for the report.
    top_use_cases: list[tuple[str, int]] = field(default_factory=list)
    top_pains: list[tuple[str, int]] = field(default_factory=list)
    intent_breakdown: dict[str, int] = field(default_factory=dict)

    @property
    def paying_count(self) -> int:
        return sum(1 for p in self.posts if p.intent == "paying")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "volume": self.volume,
            "volume_score": round(self.volume_score, 3),
            "intent_score": round(self.intent_score, 3),
            "competition": round(self.competition, 3),
            "competition_score": round(self.competition_score, 3),
            "total_score": round(self.total_score, 3),
            "rank": self.rank,
            "paying_count": self.paying_count,
            "top_use_cases": self.top_use_cases,
            "top_pains": self.top_pains,
            "intent_breakdown": self.intent_breakdown,
        }


@dataclass
class Lead:
    """A scored individual within the winning segment, with drafted outreach."""

    classified: ClassifiedPost
    lead_score: float = 0.0          # 0-1
    outreach: str = ""
    outreach_method: str = "llm"     # "llm" or "template"

    @property
    def author(self) -> str:
        return self.classified.post.author

    @property
    def handle(self) -> str:
        """Author as a single-@ handle (sources vary in whether they include one)."""
        return "@" + self.classified.post.author.lstrip("@")

    @property
    def quote(self) -> str:
        """A short, representative snippet of the person's own words."""
        text = self.classified.post.full_text.replace("\n", " ").strip()
        return (text[:220] + "…") if len(text) > 220 else text

    def to_dict(self) -> dict:
        return {
            "author": self.author,
            "source": self.classified.post.source,
            "url": self.classified.post.url,
            "segment": self.classified.segment,
            "pain": self.classified.pain,
            "use_case": self.classified.use_case,
            "intent": self.classified.intent,
            "quote": self.quote,
            "lead_score": round(self.lead_score, 3),
            "outreach": self.outreach,
            "outreach_method": self.outreach_method,
        }
