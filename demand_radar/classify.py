"""Classify — the first LLM step. Tag each post with {segment, use_case, pain, intent}.

Uses Claude when a key is available (the prompt from the project spec, extended
with product + segment context for consistent labels). Falls back per-post to a
transparent keyword heuristic so the pipeline always completes offline. Every
ClassifiedPost records which `method` produced it, so the report can be honest.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from .config import Config
from .llm import LLM
from .models import INTENT_LEVELS, ClassifiedPost, Post

# Extended from the spec's classifier prompt. Same JSON shape; adds the product
# and the candidate segment list so labels stay consistent across posts.
CLASSIFIER_SYSTEM = """You label demand signals for a product. Return strict JSON only, no prose.

Product: {product}
Candidate segments (use these labels when they fit; otherwise coin a short lowercase one): {segments}

For the post below return exactly:
{{"segment": <string>, "use_case": <short string>, "pain": <short string>, "intent": <"browsing"|"looking"|"paying">}}

Rules:
- segment: who the author is, as a market segment. If the post is NOT about the product's problem space, set segment to "none".
- use_case: the specific job they are trying to get done, in a few words.
- pain: the friction they express, in their framing, a few words.
- intent: "browsing" = idle interest; "looking" = actively seeking a solution; "paying" = already spending money/time (hiring, paying a freelancer, subscribing) to solve it.
Return JSON only."""


def _classify_llm(llm: LLM, config: Config, post: Post) -> Optional[ClassifiedPost]:
    system = CLASSIFIER_SYSTEM.format(
        product=config.product,
        segments=", ".join(config.segments_hint) or "(none provided)",
    )
    # Gemini 3.x is a thinking model — give it room so reasoning + JSON both fit.
    data = llm.complete_json(system, f"Post:\n{post.full_text}", max_tokens=1024)
    if not data or "segment" not in data:
        return None
    intent = str(data.get("intent", "browsing")).lower().strip()
    if intent not in INTENT_LEVELS:
        intent = "browsing"
    return ClassifiedPost(
        post=post,
        segment=_normalise_segment(str(data.get("segment", "none")), config),
        use_case=str(data.get("use_case", "")).strip(),
        pain=str(data.get("pain", "")).strip(),
        intent=intent,
        confidence=0.8,
        method="llm",
    )


# -- heuristic fallback -----------------------------------------------------
# Deliberately specific — a bare "$" or "paid" over-tags posts that merely mention
# money ("can't afford $30", "$800 camera"). Paying intent needs a spend signal.
_PAYING_MARKERS = (
    "hire", "hiring", "freelanc", "outsource", "budget", "retainer", "commission",
    "willing to pay", "paying $", "pay per", "per video", "per clip", "per hour",
    "/video", "/mo", "/month", "paid editor", "hire an editor", "hire someone",
)
_LOOKING_MARKERS = (
    "looking for", "recommend", "any tool", "anyone know", "how do i", "how to",
    "need a", "need someone", "suggestion", "alternative", "is there a", "best way",
    "can't find", "struggling to",
)

# Phrases that negate a paying signal ("without hiring", "can't afford an editor").
_PAYING_NEGATORS = (
    "without hiring", "without paying", "can't afford", "cant afford",
    "cannot afford", "no budget", "without an editor", "instead of hiring",
    "rather not hire", "don't want to hire",
)


def _detect_intent(text: str) -> str:
    low = text.lower()
    paying = any(m in low for m in _PAYING_MARKERS) and not any(
        n in low for n in _PAYING_NEGATORS
    )
    if paying:
        return "paying"
    if any(m in low for m in _LOOKING_MARKERS):
        return "looking"
    return "browsing"


def _detect_segment(text: str, config: Config) -> tuple[str, int]:
    """Return (segment, match_count) using per-segment keywords + hint tokens."""
    low = text.lower()
    best_segment, best_hits = "", 0
    for seg in config.segments_hint:
        keywords = config.segment_keywords.get(seg, [])
        # Always include the hint's own words as fallback keywords.
        candidates = list(keywords) + [seg] + seg.split()
        hits = sum(1 for kw in candidates if kw and kw.lower() in low)
        if hits > best_hits:
            best_segment, best_hits = seg, hits
    return best_segment, best_hits


def _classify_heuristic(config: Config, post: Post) -> ClassifiedPost:
    text = post.full_text
    low = text.lower()
    matched_pain = next((k for k in config.pain_keywords if k.lower() in low), "")
    segment, seg_hits = _detect_segment(text, config)

    relevant = bool(matched_pain) or seg_hits > 0
    if not relevant:
        return ClassifiedPost(post, "none", "", "", "browsing", 0.3, "heuristic")

    if not segment:
        segment = "other"
    return ClassifiedPost(
        post=post,
        segment=segment,
        use_case=matched_pain or "general",
        pain=matched_pain or "unspecified friction",
        intent=_detect_intent(text),
        confidence=0.4,
        method="heuristic",
    )


# -- segment normalisation --------------------------------------------------
def _normalise_segment(raw: str, config: Config) -> str:
    s = raw.lower().strip().strip(".")
    if s in ("none", "", "n/a", "irrelevant"):
        return "none"
    # Map to a hint segment when they clearly refer to the same thing.
    for seg in config.segments_hint:
        seg_l = seg.lower()
        if s == seg_l or seg_l in s or s in seg_l:
            return seg
        # token overlap
        if set(s.split()) & set(seg_l.split()):
            return seg
    return s


# -- orchestration ----------------------------------------------------------
def classify_all(
    config: Config,
    posts: list[Post],
    llm: LLM,
    max_workers: int = 3,
    logger: Callable[[str], None] = print,
) -> list[ClassifiedPost]:
    """Classify every post, concurrently when using the LLM."""
    results: list[ClassifiedPost] = []

    if not llm.available:
        logger(f"  [classify] offline mode — heuristic classifier on {len(posts)} posts")
        return [_classify_heuristic(config, p) for p in posts]

    logger(f"  [classify] classifying {len(posts)} posts with {config.model} "
           f"({max_workers} workers)")
    llm.warmup()  # build the client once in the main thread before fanning out
    done = 0
    fallbacks = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_post = {
            pool.submit(_classify_llm, llm, config, p): p for p in posts
        }
        for future in as_completed(future_to_post):
            post = future_to_post[future]
            cp = future.result()
            if cp is None:  # LLM failed for this post — fall back, stay honest
                cp = _classify_heuristic(config, post)
                fallbacks += 1
            results.append(cp)
            done += 1
            if done % 25 == 0:
                logger(f"  [classify] {done}/{len(posts)} done")

    if fallbacks:
        logger(f"  [classify] {fallbacks} posts fell back to the heuristic "
               f"(LLM error: {llm.last_error})")
    return results
