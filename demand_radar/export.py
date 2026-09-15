"""Export — the brain→arms seam.

Turns a Demand Radar run into a clean, executor-agnostic **GTM campaign** JSON
that any execution tool (Kami, a CRM, your own sender) can consume. Demand Radar
is the brain (it *derives* who to target and drafts messages); the executor is the
arms (it *sends*). This file is the contract between them — deliberately generic,
versioned, and safe by construction.

Safety is encoded in the payload, not left to the executor's goodwill:
  * every message ships as status "draft", never "sent" — Demand Radar never sends;
  * leads are gated to actionable intent tiers (paying/looking) — no cold-contacting
    people who were only browsing;
  * `guardrails` states approval + platform-ToS expectations explicitly;
  * `contactability` is honest — most leads are a public handle, not a verified email,
    so the default reach is an in-thread reply, not a cold DM.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from .config import Config

SCHEMA = "demand-radar/gtm-campaign"
SCHEMA_VERSION = "1.0"

# Map a source prefix (e.g. "hn:comments") to a normalised channel name.
_CHANNEL = {
    "hn": "hackernews",
    "hackernews": "hackernews",
    "reddit": "reddit",
    "stackexchange": "stackexchange",
    "stackoverflow": "stackexchange",
    "youtube": "youtube",
    "upwork": "upwork",
    "seed": "seed",
}


def _channel(source: str) -> str:
    prefix = source.split(":", 1)[0].strip().lower()
    return _CHANNEL.get(prefix, prefix or "unknown")


def _objective(name: str) -> str:
    n = (name or "").lower()
    if n in ("marketing", "marketing_distribution", "distribution", "content"):
        return "marketing_distribution"
    return "sales_outreach"


def to_campaign(
    config: Config,
    result,
    objective: str = "sales_outreach",
    intent_gate: tuple[str, ...] = ("paying", "looking"),
) -> dict:
    """Build the executor-agnostic campaign dict from a RunResult."""
    bh = result.beachhead
    gate = tuple(intent_gate)

    included: list[dict] = []
    excluded = 0
    for lead in result.leads:
        cp = lead.classified
        if gate and cp.intent not in gate:
            excluded += 1
            continue
        included.append({
            "id": cp.post.id,
            "handle": lead.handle,
            "source": cp.post.source,
            "source_url": cp.post.url,
            "channel": _channel(cp.post.source),
            "segment": cp.segment,
            "intent": cp.intent,
            "pain": cp.pain,
            "use_case": cp.use_case,
            "quote": lead.quote,
            "lead_score": round(lead.lead_score, 3),
            "message": {
                "draft": lead.outreach,
                "method": lead.outreach_method,   # "llm" or "template"
                "status": "draft",                # NEVER "sent" — the executor sends
                "approved": False,                # executor flips this after human review
            },
            "contactability": {
                "has_direct_contact": False,      # we hold a public handle, not a verified email
                "reach_via": "reply_in_thread" if ":" in cp.post.source else "unknown",
            },
        })
    for i, lead in enumerate(included, 1):
        lead["priority"] = i  # already ordered best-first by lead_score

    channels = sorted({l["channel"] for l in included})

    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_tool": "demand-radar",
        "product": config.product,
        "run": {
            "mode": result.meta.get("mode"),
            "model": result.meta.get("model"),
            "posts_analysed": result.meta.get("total_posts"),
        },
        "beachhead": None if not bh else {
            "segment": bh.name,
            "score": round(bh.total_score, 3),
            "volume": bh.volume,
            "intent_score": round(bh.intent_score, 3),
            "competition": round(bh.competition, 3),
            "why": (f"Highest composite score across {len(result.segments)} candidate "
                    f"segments (volume {bh.volume}, intent {bh.intent_score:.2f}, "
                    f"competition {bh.competition:.2f})."),
            "top_pains": bh.top_pains,
            "top_use_cases": bh.top_use_cases,
        },
        "campaign": {
            "objective": _objective(objective),   # sales_outreach | marketing_distribution
            "target_segment": bh.name if bh else None,
            "channels": channels,
            "lead_count": len(included),
            "excluded_low_intent": excluded,
        },
        "guardrails": {
            "drafts_only": True,
            "human_approval_required": True,
            "allowed_intent_tiers": list(gate),
            "notes": ("Executor must send; Demand Radar only drafts. Respect each "
                      "platform's ToS / anti-spam rules. Prefer in-thread replies over "
                      "cold DM/email — most leads are a public handle, not a verified contact."),
        },
        "leads": included,
    }


def write_campaign(
    path: str,
    config: Config,
    result,
    objective: str = "sales_outreach",
    intent_gate: tuple[str, ...] = ("paying", "looking"),
) -> str:
    """Write the campaign JSON to `path` and return the path."""
    data = to_campaign(config, result, objective, intent_gate)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path
