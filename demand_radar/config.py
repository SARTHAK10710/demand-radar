"""Config loading — the one file you swap to re-target Demand Radar at any product.

A config declares WHAT product we're hunting demand for, WHICH pain phrases mark
that demand, WHERE to look, and a HINT list of segments to bias clustering toward.
Everything else in the pipeline is product-agnostic and reads from here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is a declared dependency
    yaml = None


@dataclass
class RankWeights:
    """How much each factor matters when scoring a segment (need not sum to 1)."""

    volume: float = 0.4
    intent: float = 0.4
    competition: float = 0.2


@dataclass
class Config:
    product: str
    pain_keywords: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    segments_hint: list[str] = field(default_factory=list)

    # Optional knobs — sensible defaults so a minimal config still runs.
    name: str = "product"
    seed_file: str = ""                       # path to a seed .jsonl of posts (offline demo)
    # Optional per-segment keyword lists — sharpen the offline heuristic classifier.
    segment_keywords: dict[str, list[str]] = field(default_factory=dict)
    competitor_keywords: list[str] = field(default_factory=list)
    competition_override: dict[str, float] = field(default_factory=dict)
    rank_weights: RankWeights = field(default_factory=RankWeights)
    max_posts_per_source: int = 150
    lead_count: int = 10                      # how many leads to draft outreach for
    provider: str = "auto"                    # auto | gemini | openai | anthropic
    model: str = "gemini-3.6-flash"           # model id (provider default used if it mismatches)

    @classmethod
    def from_dict(cls, data: dict[str, Any], base_dir: str = "") -> "Config":
        weights = data.get("rank_weights", {}) or {}
        seed_file = data.get("seed_file", "")
        if seed_file and base_dir and not os.path.isabs(seed_file):
            seed_file = os.path.join(base_dir, seed_file)
        return cls(
            product=data["product"],
            pain_keywords=list(data.get("pain_keywords", [])),
            sources=list(data.get("sources", [])),
            segments_hint=list(data.get("segments_hint", [])),
            name=data.get("name", "product"),
            seed_file=seed_file,
            segment_keywords={k: list(v) for k, v in (data.get("segment_keywords", {}) or {}).items()},
            competitor_keywords=list(data.get("competitor_keywords", [])),
            competition_override=dict(data.get("competition_override", {})),
            rank_weights=RankWeights(
                volume=float(weights.get("volume", 0.4)),
                intent=float(weights.get("intent", 0.4)),
                competition=float(weights.get("competition", 0.2)),
            ),
            max_posts_per_source=int(data.get("max_posts_per_source", 150)),
            lead_count=int(data.get("lead_count", 10)),
            provider=str(data.get("provider", "auto")),
            model=data.get("model", "gemini-3.6-flash"),
        )

    @classmethod
    def load(cls, path: str) -> "Config":
        if yaml is None:
            raise RuntimeError("PyYAML is required to load configs. `pip install pyyaml`.")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data or "product" not in data:
            raise ValueError(f"Config {path!r} must define at least a 'product' field.")
        return cls.from_dict(data, base_dir=os.path.dirname(os.path.abspath(path)))
