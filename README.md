# Demand Radar

**A product-agnostic GTM tool that *derives* a product's ICP from real demand signals, instead of guessing it.**

Point it at any product via a single config file. It mines where people express the
product's core pain, classifies and clusters those signals into segments, sizes each
one, recommends the **beachhead** segment to attack first, and hands you a **scored
lead list with drafted outreach** for that segment.

> Most people walk into a GTM conversation and *assert* an ICP. Demand Radar *derives*
> it — from evidence, not a hunch.

---

## The idea in one line

Mine where people express a product's core pain → classify and cluster those signals
into segments → size each → rank on volume, intent, and competition → recommend the
beachhead → draft outreach for its top leads.

## How it works, end to end

Config-driven, so the same tool runs for any product by swapping one file.

| Stage | What happens |
|------|--------------|
| **1. Ingest** | Pull posts from real, live sources (Hacker News, Stack Exchange, Reddit). |
| **2. Classify** | An LLM step (Gemini / OpenAI / Claude — auto-detected) tags each post: `segment`, `use_case`, `pain`, and `intent` (`browsing` / `looking` / `paying`). |
| **3. Cluster + size** | Group tagged posts into segments and count volume — an *empirically sized* set of candidate ICPs. |
| **4. Rank** | Score each segment on **volume**, **intent**, and **rough competition**. Output the recommended beachhead. |
| **5. Actionable layer** | For the winning segment, score a lead list and draft a personalised, non-salesy first message per lead. |

The two LLM steps are **provider-agnostic** — set a `GEMINI_API_KEY`, `OPENAI_API_KEY`,
or `ANTHROPIC_API_KEY` and Demand Radar auto-detects which to use (connect Gemini → Gemini,
OpenAI → OpenAI, Claude → Claude). Force one with `provider:` in the config or `--provider`.
**No API key? It still runs** — every LLM step degrades to a transparent keyword heuristic,
and each result records which `method` produced it. So it's always demoable, and honest
about how each label was made.

---

## Quickstart

```bash
pip install -r requirements.txt

# Real, live data + real LLM classification (recommended)
export GEMINI_API_KEY=AIza...            # free key: https://aistudio.google.com/apikey
# ...or OPENAI_API_KEY / ANTHROPIC_API_KEY — the provider is auto-detected
python -m demand_radar configs/ai_test_writer.yaml --live-ingest

# No key? Still runs on real data with the offline heuristic classifier
python -m demand_radar configs/ai_test_writer.yaml --live-ingest --offline
```

Each run prints a terminal summary and writes three files to `outputs/`:

- `<name>_report.html` — a styled, self-contained page (the live-demo artifact)
- `<name>_report.md` — a shareable Markdown report
- `<name>_results.json` — the full structured result (real source URLs included)

### CLI flags

| Flag | Effect |
|------|--------|
| `--live-ingest` | Pull posts live from the configured sources. |
| `--offline` | Force heuristic mode; never call the LLM (no key needed). |
| `--live` | Force LLM mode even if no key is auto-detected. |
| `--leads N` | Number of leads to draft outreach for (default from config). |
| `--max-posts N` | Cap total posts analysed — handy for API rate/quota budgets. |
| `--export` | Also write a **GTM handoff JSON** (the brain→arms seam). |
| `--export-format` | `generic` (default) or `kami` — Kami-contract demand signals + segment sizing. |
| `--export-objective` | `sales` (default) or `marketing` — objective for generic `--export`. |
| `--provider` | `auto` (default), `gemini`, `openai`, or `anthropic`. |
| `--model ID` | Override the model id (provider default is used if it mismatches the provider). |
| `--outdir DIR` | Where to write reports (default `outputs/`). |
| `--quiet` | Suppress step-by-step logging. |

---

## Data sources (all real)

| Source string | What it hits | Reachability |
|---------------|--------------|--------------|
| `hn:comments` | Hacker News comments + stories via the open **Algolia** API | Works anywhere, no auth |
| `stackexchange:<site>` | Questions via the open **Stack Exchange** API (`stackoverflow`, `softwareengineering`, …) | Works anywhere, no auth |
| `reddit:r/<sub>` | Subreddit search via reddit's public JSON | Works from a **residential** IP; data-center IPs get 403 |

Every source fails soft — if one is rate-limited or blocked, the run completes on
whatever real data it could reach. Freelance marketplaces (Upwork/Fiverr) and YouTube
comments have no free API; they can be layered in via an optional `seed_file` (JSONL).

> **Heuristic vs. Gemini on real data:** real posts rarely announce their segment in
> so many words, so the offline keyword heuristic leaves a chunk *unsegmented* and
> mislabels some intent. That's the whole reason the LLM step exists — with a Gemini
> key, segmentation and intent sharpen dramatically. The report always reports the
> `unsegmented` count so you can see the difference.

---

## Re-target it at any product

Swap one config file. Everything downstream is product-agnostic. Two example configs ship:

- [`configs/ai_test_writer.yaml`](configs/ai_test_writer.yaml) — a dev tool; runs on **100% live** HN + Stack Exchange + Reddit data.
- [`configs/shortform_video.yaml`](configs/shortform_video.yaml) — the short-form-video tool; uses a hand-built offline seed set plus optional live Reddit.

```yaml
name: ai_test_writer
product: "An AI tool that automatically writes and maintains unit tests for your codebase"
pain_keywords: ["writing tests", "flaky tests", "test coverage", "untested code"]
sources: ["hn:comments", "stackexchange:stackoverflow", "reddit:r/programming"]
segments_hint: ["indie hacker", "startup", "enterprise", "open source maintainer", "data engineer"]

# Optional knobs
segment_keywords: { startup: ["startup", "founder", "mvp"] }   # sharpen offline heuristic
competitor_keywords: ["copilot", "pytest", "diffblue"]         # rough competition proxy
competition_override: { enterprise: 0.5 }                      # manual estimate 0..1
rank_weights: { volume: 0.4, intent: 0.4, competition: 0.2 }
lead_count: 10
model: gemini-3.6-flash
```

To point it at a different product, write a new `configs/<product>.yaml` and run it.

---

## How the beachhead is scored

Each segment gets three factors, normalised to `0–1`:

- **volume** — cluster size relative to the biggest segment
- **intent** — average of `browsing`(1) / `looking`(2) / `paying`(3), mapped to `0–1`
- **competition** — a rough crowdedness estimate (per-segment override, else the share
  of posts already naming an incumbent tool). Inverted so *emptier scores higher*.

```
score = (w_volume · volume) + (w_intent · intent) + (w_competition · (1 − competition))
```

The top-scoring segment is the recommended beachhead — the smallest winnable market
with the strongest, least-contested demand. Weights are configurable. The catch-all
"unsegmented" bucket is reported but never recommended as a beachhead.

## The brain→arms seam (`--export`)

Demand Radar is the **brain** — it *derives* who to target and drafts messages. Pair it
with an **executor** (a GTM tool like [Kami](https://www.trykami.app/), a CRM, or your own
sender — the **arms**) and you get a closed loop: *derive → execute → measure → re-rank*.

`--export` writes a clean, versioned, **executor-agnostic** campaign contract
(`outputs/<name>_campaign.json`, schema `demand-radar/gtm-campaign`) that any executor can
consume. Safety is baked into the payload, not left to the executor:

- every message ships as `status: "draft"` — **Demand Radar never sends**;
- leads are **gated to actionable intent** (`paying`/`looking`) — no cold-contacting browsers;
- `guardrails` states human-approval + platform-ToS expectations explicitly;
- `contactability` is honest — most leads are a public handle, so the default reach is an
  in-thread reply, not a cold DM.

```bash
python -m demand_radar configs/ai_test_writer.yaml --live-ingest --export
```

**Kami-native handoff:** `--export-format kami` maps the run onto [Kami's](https://www.trykami.app)
typed contracts — every mined post becomes an `AccountSignal` (`signal_type: community_post`) and
every segment gets an evidence-based `demand_volume` + `recommended_tier`. This adds the
**bottom-up demand sizing** Kami's top-down `icp_segmentation` lacks. Packaged as a Kami skill in
[`contrib/kami/`](contrib/kami/).

```bash
python -m demand_radar configs/ai_test_writer.yaml --live-ingest --export --export-format kami
```

## Scope, honestly

The data layer is deliberately scrappy. A few hundred posts is enough to prove the
logic. **The point is the system and the thinking, not data volume.** Live ingestion
pulls genuine posts with clickable source URLs; the optional seed set is only for
running fully offline.

---

## Project layout

```
demand_radar/
  config.py     # the one file you swap to re-target
  ingest.py     # real connectors: Hacker News, Stack Exchange, Reddit (+ optional seed)
  classify.py   # LLM step 1 with Gemini (+ transparent heuristic fallback)
  cluster.py    # group + size into candidate segments
  rank.py       # score segments, pick the beachhead
  outreach.py   # LLM step 2 — scored leads + drafted messages
  report.py     # console / markdown / html / json renderers
  llm.py        # the ONLY file that talks to a model — Gemini / OpenAI / Claude, auto-detected
  pipeline.py   # orchestrates the six stages
  cli.py        # command-line entry point
configs/        # product configs (YAML)
data/seeds/     # optional offline seed sets (JSONL)
outputs/        # generated reports
tests/          # smoke + unit tests
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## Notes

- **LLM provider:** everything model-specific lives in `llm.py`, which auto-detects Gemini /
  OpenAI / Claude from whichever API key is set (install that provider's SDK — see
  `requirements.txt`). The rest of the pipeline never touches a provider.
- **Outreach is drafted, never sent.** The tool writes first-message drafts for review;
  it does not contact anyone.
