---
name: demand_signal_mining
description: Mine dated, sourced community-post buying signals (Reddit / Hacker News / Stack Overflow) and size demand per segment. Use to populate community_post AccountSignals and give icp_segmentation an evidence-based sizing axis — especially for PLG/self-serve segments where there is no company to research.
---

# Demand Signal Mining (bottom-up)

`icp_segmentation` derives segments **top-down** from the seller's positioning; `signal_research`
finds account signals (funding, hiring, launches). Neither **measures real demand**. This skill
adds the missing bottom-up axis: it reads where people actually express the product's pain,
tags how ready-to-buy they are, and **sizes each segment by real volume**.

**Scope & execution:** an *inbound research* skill — it produces signals and sizing; it never
sends or publishes, and adds no new outbound surface. Hermes executes it with the workspace's
BYOK model like any other Kami skill — **no external service, hosted API, or custom LLM wrapper
required.**

## Method

1. From the confirmed dossier, take the product one-liner + its core pain, and derive a small
   set of **pain phrases** and **candidate segments** (do not inject a hardcoded vertical).
2. Search demand sources for those pain phrases: **Reddit** subreddits, **Hacker News**,
   **Stack Overflow / Stack Exchange** (community-post surfaces Kami already recognises).
3. For each post, classify: `{segment, pain, use_case, intent}` where **intent** is one of
   `browsing` (idle interest) | `looking` (actively seeking a solution) | `paying` (already
   spending money/time to solve it). If irrelevant, drop it.
4. **Cluster** posts by segment and **count volume** per segment — this is the empirical size.
5. Emit two things: `community_post` signals (one per post) and a per-segment **demand size**.

## Hard rules

- **Never fabricate** a post, quote, pain, or volume. Every signal must carry a reachable
  `source_url`.
- `observed_at` is the **post's own date**, not today. Posts older than 90 days: lower
  `confidence`; do not use as a fresh hook.
- **Never invent emails.** These are public handles. For PLG/self-serve segments the reachable
  action is an **in-thread reply** routed to *Create distribution* — not a cold consumer email.
- Ranking is **Fit × Intent × size**; keep them separate axes. Demand volume sizes a segment; it
  does not by itself prove fit.
- `recommended_tier` is a **demand-priority hint, not a fit tier**. Never Tier-1 a segment on
  demand volume alone — Kami's fit-based tiering governs, and accounts bind to segment + signal + source.
- Wait for founder **confirmation** of the dossier before mining.

## Output

- **Signals** — `AccountSignal` records with `signal_type: "community_post"`
  (`provider`, `detail`, `source_url`, `observed_at`, `confidence`, `evidence_text`), each tagged
  with its `segment` and `intent`.
- **Segment sizing** — per segment: `demand_volume`, `intent_mix`, a demand score, a
  `recommended_tier` (1 = attack first), and up to 5 `evidence_urls`. Feeds
  `icp_segmentation` / `SalesPlanTier.target_count` with evidence instead of a guessed budget.

Hermes runs this skill and persists the records through the accounts/signals API (never held
only in agent memory). A reference for the exact JSON output shape — **contract only, not a
dependency** — lives in Demand Radar: `demand_radar/export.py::to_kami`
(https://github.com/SARTHAK10710/demand-radar).
