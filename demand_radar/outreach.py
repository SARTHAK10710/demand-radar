"""Outreach — the actionable layer and second LLM step.

For the winning (beachhead) segment only, score its posts as individual leads and
draft a short, non-salesy first message per lead. Uses Claude when available (the
outreach prompt from the project spec); falls back to a peer-toned template so a
lead list with drafted messages always comes out the far end.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .config import Config
from .llm import LLM
from .models import Lead, Segment

OUTREACH_SYSTEM = """Write a 3-sentence, non-salesy first message to this person.
Reference their specific pain in their own words. Offer the product as a faster
path, not a pitch. No emojis. Sound like a helpful peer, not marketing.

Product: {product}
Return only the message text, nothing else."""


def _lead_score(classified) -> float:
    """0-1 priority score for a post-as-lead within the beachhead segment."""
    intent_norm = (classified.intent_weight - 1.0) / 2.0        # browsing 0 .. paying 1
    pain_specific = 1.0 if classified.pain and classified.pain not in (
        "unspecified friction", "general", "",
    ) else 0.4
    engagement = min(classified.post.score / 50.0, 1.0)
    return round(
        0.5 * intent_norm + 0.25 * pain_specific + 0.15 * classified.confidence
        + 0.10 * engagement,
        3,
    )


def _draft_llm(llm: LLM, config: Config, lead: Lead) -> str | None:
    system = OUTREACH_SYSTEM.format(product=config.product)
    context = (
        f"Lead context:\n"
        f"- segment: {lead.classified.segment}\n"
        f"- pain: {lead.classified.pain}\n"
        f"- use case: {lead.classified.use_case}\n"
        f'- their words: "{lead.quote}"'
    )
    return llm.complete_text(system, context, max_tokens=1024)


def _draft_template(config: Config, lead: Lead) -> str:
    pain = lead.classified.pain or "the thing you're wrestling with"
    return (
        f"Saw your note about {pain} — I've hit that exact wall myself. "
        f"I've been using {config.product}, and it's cut that part down from "
        f"a slog to a few minutes. Happy to show you how I set it up if it's useful, "
        f"no strings."
    )


def build_leads(
    config: Config,
    segment: Segment,
    llm: LLM,
    logger: Callable[[str], None] = print,
) -> list[Lead]:
    """Score the segment's posts, take the top N, and draft outreach for each."""
    leads = [Lead(classified=cp, lead_score=_lead_score(cp)) for cp in segment.posts]
    leads.sort(key=lambda l: l.lead_score, reverse=True)
    leads = leads[: config.lead_count]

    if not leads:
        return leads

    if llm.available:
        logger(f"  [outreach] drafting {len(leads)} messages with {config.model}")

        def _fill(lead: Lead) -> Lead:
            msg = _draft_llm(llm, config, lead)
            if msg:
                lead.outreach, lead.outreach_method = msg.strip(), "llm"
            else:
                lead.outreach, lead.outreach_method = _draft_template(config, lead), "template"
            return lead

        with ThreadPoolExecutor(max_workers=4) as pool:
            leads = list(pool.map(_fill, leads))
    else:
        logger(f"  [outreach] offline mode — templated messages for {len(leads)} leads")
        for lead in leads:
            lead.outreach = _draft_template(config, lead)
            lead.outreach_method = "template"

    return leads
