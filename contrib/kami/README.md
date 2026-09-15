# Kami contribution — bottom-up demand signals

This folder packages Demand Radar's distinctive capability as a **Kami** contribution
(Kami = the open-source AI GTM agent, https://www.trykami.app). It's additive, not a rewrite:
it fills the one gap Kami's own skills leave open.

## What it adds (in one sentence)

Kami's `icp_segmentation` reasons segments **top-down** from your domain; this adds **bottom-up
demand sizing** — it measures how big each segment really is by mining and classifying real
pain posts, and emits them as `community_post` signals Kami's contract already defines.

## Why it's useful to Kami (not redundant)

| Kami today | Gap | This contribution |
|---|---|---|
| `icp_segmentation` — top-down from positioning | No **measured** demand size | Empirical `demand_volume` per segment |
| `signal_research` — funding/hiring/launch signals | `community_post` type exists but isn't mined | Populates `community_post` `AccountSignal`s, sourced + dated |
| B2B strong; **PLG/self-serve thin** ("find people to reach", no invented emails) | Needs real in-thread opportunities | Real people expressing the pain, reachable in-thread |

## Contract mapping (→ `contracts/contracts.ts`)

- **Each mined post → `AccountSignal`**: `provider`, `signal_type: "community_post"`, `detail`,
  `source_url`, `observed_at` (post date), `confidence` (decayed >90d), `evidence_text`
  (+ our `segment` and `intent` tags).
- **Each segment → sizing** for `icp_segmentation` / `SalesPlanTier.target_count`:
  `demand_volume`, `intent_mix`, `recommended_tier`, `evidence_urls`.

Intent tiers (`browsing` → `looking` → `paying`) map onto Kami's Fit × **Intent** scoring
(`LeadScore.factors.intent`) as a *demand-expression* intent, complementing account-event intent.

## Files

- `skills/demand_signal_mining/SKILL.md` — the skill, written in Kami's skill format
  (matches the style of `icp_segmentation` / `signal_research`).
- Reference implementation producing the exact JSON shape lives in the Demand Radar repo:
  `demand_radar/export.py::to_kami`. Generate a sample:
  ```bash
  python -m demand_radar configs/ai_test_writer.yaml --live-ingest --export --export-format kami
  # -> outputs/ai_test_writer_kami.json
  ```

## Safety alignment (matches Kami's non-negotiables)

Never fabricate; every signal has a reachable `source_url`; `observed_at` is the event date;
never invent emails; PLG reach is an in-thread reply routed to *Create distribution*; the
executor + human approval gate every real action.

## How to open the PR (per Kami's CONTRIBUTING.md)

1. **Confirm the canonical repo first** — Demand Radar's notes saw both
   `github.com/kami-community/kami` and `github.com/saranambiar/kami`. Ask the maintainer which.
2. Branch from **`dev`** (PR base = `dev`, **not** `main`): `git checkout dev && git checkout -b feature/demand-signal-mining`.
3. Add `skills/demand_signal_mining/SKILL.md`; run `npm run sync:skills`.
4. Add a small eval fixture and run `npm run eval:sales` + `npm run build`.
5. PR description: **what** (bottom-up demand sizing + community_post signals), **why**
   (empirical size axis + PLG demand discovery), **how to verify** (sample JSON + fixture).
