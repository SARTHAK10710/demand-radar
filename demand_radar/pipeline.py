"""Pipeline — orchestrate the six stages end to end.

    ingest → classify → cluster → size → rank → actionable (leads + outreach)

Same tool, any product: everything downstream reads from the Config, so pointing
Demand Radar at a new product is a one-file swap.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from . import classify as classify_mod
from . import cluster as cluster_mod
from . import ingest as ingest_mod
from . import outreach as outreach_mod
from . import rank as rank_mod
from . import report as report_mod
from .config import Config
from .llm import LLM
from .models import Lead, Segment


@dataclass
class RunResult:
    config: Config
    segments: list[Segment]
    leads: list[Lead]
    meta: dict[str, Any]
    paths: dict[str, str] = field(default_factory=dict)

    @property
    def beachhead(self) -> Segment | None:
        return self.segments[0] if self.segments else None


def run(
    config: Config,
    live_ingest: bool = False,
    prefer_offline: bool = False,
    force_live: bool = False,
    outdir: str = "outputs",
    write: bool = True,
    max_posts: int | None = None,
    logger: Callable[[str], None] = print,
) -> RunResult:
    t0 = time.time()

    logger("▸ 1/6 ingest")
    posts = ingest_mod.ingest(config, live=live_ingest, logger=logger)
    if max_posts and len(posts) > max_posts:
        posts = posts[:max_posts]
        logger(f"  [ingest] capped to {max_posts} posts (rate/quota budget)")

    llm = LLM(model=config.model, provider=config.provider,
              prefer_offline=prefer_offline, force_live=force_live)
    mode = "live" if llm.available else "offline"

    logger(f"▸ 2/6 classify  ({mode})")
    classified = classify_mod.classify_all(config, posts, llm, logger=logger)
    relevant = [c for c in classified if c.is_relevant]

    logger("▸ 3/6 cluster")
    all_segments = cluster_mod.cluster(classified)
    # "other" is a catch-all for relevant-but-unsegmented posts — keep it out of
    # the ranked ICPs (it should never be recommended as a beachhead), but report
    # its size honestly: it's a signal of how much the classifier couldn't place.
    catch_all = {"other", "unsegmented"}
    segments = [s for s in all_segments if s.name not in catch_all]
    unsegmented = sum(s.volume for s in all_segments if s.name in catch_all)
    logger(f"  [cluster] {len(segments)} candidate segments "
           f"({unsegmented} relevant posts unsegmented)")

    logger("▸ 4/6 size + 5/6 rank")
    segments = rank_mod.rank(segments, config)
    bh = rank_mod.beachhead(segments)
    if bh:
        logger(f"  [rank] beachhead → {bh.name} (score {bh.total_score:.2f})")

    logger("▸ 6/6 actionable layer (leads + outreach)")
    leads = outreach_mod.build_leads(config, bh, llm, logger=logger) if bh else []

    meta = {
        "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "mode": mode,
        "provider": llm.provider if mode == "live" else None,
        "model": llm.model if mode == "live" else config.model,
        "total_posts": len(posts),
        "relevant_posts": len(relevant),
        "unsegmented": unsegmented,
        "sources": config.sources,
        "elapsed_s": round(time.time() - t0, 2),
    }

    paths: dict[str, str] = {}
    if write:
        paths = report_mod.write_outputs(outdir, config, segments, leads, meta)
        logger(f"  [report] wrote {', '.join(paths.values())}")

    logger(f"✓ done in {meta['elapsed_s']}s")
    return RunResult(config, segments, leads, meta, paths)
