# Demand Radar — Project Memory

> Living context doc: **what this is**, **how we built it**, and **where it's going**.
> Read this first to get back up to speed in one page.

---

## 1. About Demand Radar (what it is)

A **product-agnostic GTM tool that *derives* a product's Ideal Customer Profile (ICP)
from real demand signals, instead of guessing it.**

Point it at any product via one config file. It mines where people express the
product's core pain, classifies and clusters those signals into segments, sizes each,
recommends the **beachhead** segment to attack first, and produces a **scored lead list
with drafted (never sent) outreach** for that segment.

**The thesis:** most people *assert* an ICP ("I think devs will like this"). Demand
Radar *derives* it from evidence ("the data says start with open-source maintainers —
here's who and what to say").

**Repo:** https://github.com/SARTHAK10710/demand-radar (public)
**Owner/GitHub:** SARTHAK10710 · **Local path:** `C:\Users\negis\Downloads\demand-radar`

---

## 2. How it works (the pipeline)

Config-driven; the same engine runs for any product by swapping one YAML file.

```
ingest → classify → cluster + size → rank → beachhead → actionable (leads + outreach)
```

| Stage | What happens |
|------|--------------|
| **Ingest** | Pull real posts from live sources (Hacker News, Stack Exchange, Reddit) + optional seed JSONL |
| **Classify** | LLM (Google Gemini) tags each post: `segment`, `use_case`, `pain`, `intent` (browsing → looking → paying). Heuristic fallback if no key. |
| **Cluster + size** | Group tagged posts into segments, count volume → empirically sized candidate ICPs |
| **Rank** | Score each on volume + intent + rough competition → recommended beachhead |
| **Outreach** | For the winning segment: scored lead list + a drafted, non-salesy first message per lead |

---

## 3. What's built & how (the journey / key decisions)

- **Language/stack:** Python. LLM behind a single wrapper (`demand_radar/llm.py`) so the
  provider is swappable in one file.
- **LLM provider:** **provider-agnostic** — auto-detects Gemini / OpenAI / Claude from
  whichever API key is set (connect Gemini → Gemini, OpenAI → OpenAI, Claude → Claude);
  `provider:` config or `--provider` forces one. Default Gemini (`gemini-3.6-flash`, free tier);
  defaults `gpt-4o-mini` / `claude-haiku-4-5`. No key → offline heuristic. (History: Claude →
  Gemini at owner's request → now all three.) In the Kami contribution this is moot — Hermes
  (BYOK) runs the skill with the user's own model.
- **"Offline" = no-LLM mode**, NOT no-internet: heuristic keyword classifier + templated
  outreach; `--live-ingest` still pulls real posts. It's the always-runs fallback.
- **MCP social connectors (LinkedIn/X/etc.): NOT built yet** — still just an idea (roadmap
  lever #3). Live connectors today = HN, Stack Exchange, Reddit + seed loader.
  - Gotcha we hit: `gemini-2.5-flash` is deprecated for new users → use 3.6-flash.
  - Gotcha we hit: Gemini 3.x is a **thinking model** — a small `max_tokens` (300) got
    eaten by internal reasoning → raised to **1024** so JSON completes.
  - Added **429 retry/backoff** + lower concurrency for rate limits.
- **Real data connectors (`demand_radar/ingest.py`):**
  - `hn:` — Hacker News via the open Algolia API (works anywhere) ✅
  - `stackexchange:<site>` — Stack Exchange open API ✅
  - `reddit:r/<sub>` — public JSON (works on a **residential** IP; data-center IPs get 403)
  - Seed `.jsonl` loader for offline / no-API sources.
- **Degrades gracefully:** with no `GEMINI_API_KEY` it runs fully offline (heuristic
  classify + templated outreach), and every result records which `method` produced it.
- **Reports:** console + Markdown + **theme-aware HTML** (light/dark toggle, score ring,
  intent pills, per-lead copy buttons) + JSON.
- **Configs shipped:**
  - `configs/ai_test_writer.yaml` — a dev tool; runs on **100% live** HN + Stack Exchange + Reddit data.
  - `configs/shortform_video.yaml` — short-form-video tool; offline **synthetic** seed set + optional live Reddit.
- **Tests:** `tests/test_pipeline.py` (10 passing — JSON extraction, intent negation, ranking, full offline run).
- **Run-in-browser:** `demand_radar_colab.ipynb` →
  https://colab.research.google.com/github/SARTHAK10710/demand-radar/blob/main/demand_radar_colab.ipynb
- **Live demo artifact (private, owner controls sharing):**
  https://claude.ai/code/artifact/8c245f76-881a-4832-bd96-137fb90cbb47
- **CLI flags:** `--live-ingest`, `--offline`, `--live`, `--leads N`, `--model ID`,
  `--max-posts N`, `--outdir`, `--quiet`.

**Proof the LLM step earns its place:** on live data, Gemini correctly labeled several
"Ask HN: Who's hiring?" posts as `none` — noise a keyword filter would have counted as demand.

---

## 4. Hard constraints we learned

- **Gemini free tier = 20 requests / DAY** (and 5 / minute) for `gemini-3.6-flash`.
  A full 186-post live run isn't feasible on free tier → needs billing or a `--max-posts`
  cap. This is the real bottleneck, not the code.
- Reddit blocks data-center IPs (403 in sandboxes) — works on a normal home connection.
- Upwork / Fiverr / YouTube: no free API → seed-set only for now.

---

## 5. What we're building next (the vision)

**Combine the "brain" (Demand Radar) with "arms" (an executor like Kami — trykami.app)
into a closed-loop GTM engine.**

- **Demand Radar = brain:** decides *who* to target and *where to start* (derivation + sizing).
- **Kami = arms:** *executes* — find, draft, **send** outreach / publish content (with approval gates).
- **The loop (the moat):** execution outcomes (opened / replied / converted per segment)
  feed **back** into Demand Radar as a `conversion:` signal → re-rank segments on **proven**
  results, not just predicted intent. The *derived* ICP becomes a *validated* ICP.

**How Kami actually works (from trykami.app):**
1. Enter your **domain** → Kami builds a **dossier about *you*** (the seller) → you confirm "that's us".
2. Choose **Find customers (Sales)** or **Create distribution (Marketing)**.
3. **Approve small batches** before anything sends or posts (human-in-loop).
4. Conversational — "ask Kami anytime," grounded in live campaign state.

**Where the seam is (sharpened):** Kami knows *who you are* (dossier from your domain) but
**does not empirically derive & rank *who wants you*** from external demand. That's Demand
Radar's differentiator.

### Kami repo — grounded findings (read 2026-09-16)
Repo read: `github.com/kami-community/kami` (docs also reference `github.com/saranambiar/kami`
— **confirm the canonical fork before opening a PR**).
- **Stack:** Next.js `web/` + **Hermes** agent gateway (`:8642`) + Supabase; TypeScript; MIT.
  Heavy to run locally (Hermes + DB migrations 001–010 + model key).
- **Skills-first:** extend via `skills/<name>/SKILL.md` — "prefer skills over hardcoded prompts."
  New platform = skill + opportunity contract (URL, evidence, why_now, draft, risks).
- **Typed contracts** (`contracts/contracts.ts`): `Account`, `AccountSignal`
  (provider, signal_type, detail, source_url, observed_at, confidence, evidence_text),
  `LeadScore` (factors: fit/intent/contactability/priority), `SalesPlan`+`SalesPlanTier`,
  `Prospect`, `Draft`, `Signal` (types include **`community_post`**). `SalesSegment` lives in
  `web/lib/salesTypes.ts`.
- **Safety (matches Demand Radar's guardrails):** never invent emails; PLG/D2C never blast →
  route to distribution; stop-before-send; founder approval; suppression/DNC; real receipts for
  "done"; sources with dated URLs (<90d); no fixture greens.
- **Contributing:** PR base = **`dev`** (NOT main); branch `feature/…`; small/scoped; add a
  `SKILL.md` with sources + an eval fixture; run `npm run eval:sales` + `npm run build`; rejected
  if it weakens safety/evals or mocks sends.

**Sharpened differentiator:** Kami's `icp_segmentation` is **top-down** (3–5 segments reasoned
from the seller's domain positioning); `signal_research` finds account signals (funding/hiring).
**Neither sizes segments by measured external demand.** Demand Radar is **bottom-up demand
sizing** — the missing empirical axis.

### Revised integration plan (better than a mega-merge)
Contribute Demand Radar's distinctive capability *into* Kami (skills-first, its native path):
- **(a) A new skill `demand_signal_mining`** ✅ BUILT (`contrib/kami/skills/demand_signal_mining/SKILL.md`)
  — mine/cluster/**size**/rank segments from real demand + emit `community_post` signals.
  Complements `icp_segmentation` by adding the empirical sizing axis it lacks.
- **(b) The `community_post` signal mapping** ✅ BUILT — Demand Radar's classified pain posts map
  1:1 onto `AccountSignal` (provider, source_url, observed_at, confidence, evidence_text + our
  segment/intent tags), via `--export --export-format kami` (`demand_radar/export.py::to_kami`,
  schema `kami/demand-signals`). `contrib/kami/README.md` has the contract mapping + PR steps.
- **Still TODO before PR:** confirm canonical Kami repo (kami-community vs saranambiar); add an
  eval fixture; open `feature/demand-signal-mining` PR against **`dev`**.
- **Honest:** Kami is broad + heavy to run; the realistic, high-value win is a **focused,
  accepted skill/provider PR**, not merging two products. That PR (into a real OSS project) +
  the Demand Radar repo behind it is a strong interview story.

```
BRAIN (derive → rank → beachhead → leads+drafts)
   → ARMS (send / publish, gated)
   → OUTCOMES (reply/convert per segment)
   → back into BRAIN (re-rank on real conversion)
```

### Roadmap
- **v0 — the seam ✅ DONE:** `demand-radar … --export` writes an **executor-agnostic GTM
  campaign JSON** (`demand_radar/export.py`, schema `demand-radar/gtm-campaign` v1.0) →
  `outputs/<name>_campaign.json`. Contains: product, beachhead + `why`, and per-lead
  {handle, source_url, channel, intent, pain, quote, lead_score, priority, message.draft,
  contactability}. Safety baked in: every message `status:"draft"` (never sent), leads gated
  to `paying`/`looking` intent, explicit `guardrails` block. Needs nothing from Kami.
- **v1 — integrated trigger:** Demand Radar launches a Kami campaign directly from the beachhead list.
- **v2 — closed loop:** Kami writes outcomes to a shared store; Demand Radar ingests them
  as a `conversion:` source and re-ranks.
- **Open-source play:** contribute a "Demand Radar import" PR to Kami (stronger for interviews than another solo repo).

### Making it work for *any* product (levers)
1. **Config auto-gen:** an `init "<product description>"` command that LLM-generates
   `pain_keywords`, `segments_hint`, and suggested `sources` → "any product" in ~10s.
2. **More connectors:** G2 / Product Hunt / LinkedIn (B2B), Amazon / TikTok / App Store
   reviews (consumer), Yelp / Nextdoor (local). Each is a small module like the HN one.
   Seed-set loader already covers anything with no API.
3. **MCP-backed ingestion (owner's idea — strong):** instead of hand-writing a scraper per
   platform, add an `mcp:` connector that pulls demand signals through **MCP servers the user
   authorizes** (Reddit, X, Gmail, web search, GitHub, …). One protocol → many sources; auth
   lives in the MCP server (no per-platform credential juggling); sidesteps IP-block/scraping
   pain (e.g. the Reddit 403). Fits our scrappy volumes. Caveats: MCP is query-oriented (not
   bulk ETL) and server quality varies. Config would gain an `mcp_servers` block; Demand Radar
   hosts a Python MCP client and maps tool results → Posts. **Distinct from Kami's channel
   connections**, which are *outbound* (send); this is *inbound* (collect). Bonus inverse idea:
   expose Demand Radar itself **as** an MCP server so any agent host can call `derive_icp(product)`.

---

## 6. Guardrails / principles (don't regress these)

- **Drafts, never sends.** Demand Radar only drafts outreach. If wired to an executor,
  gate real sends on **`paying`/`looking` intent only**, keep **human approval**, and respect
  platform ToS / anti-spam (CAN-SPAM, Reddit/HN rules). Consent is the #1 real-world risk.
- **Honest scoping.** Scrappy data layer is fine — the point is the system and the reasoning,
  not data volume. Always report `mode`, `method`, and `unsegmented` count transparently.
- **Never commit secrets.** `GEMINI_API_KEY` lives in the environment / `.env` (gitignored),
  never in the repo. `outputs/` (which may contain real handles) is gitignored.
- **Public-artifact privacy.** Don't broadcast real individuals' handles + outreach without
  the owner's informed choice; artifacts are private by default.

---

## 7. Status snapshot (2026-09-16)

- Repo live, tests green (11).
- Gemini integration verified working on `gemini-3.6-flash` (blocked only by the 20/day free quota).
- **v0 `--export` adapter shipped** (`demand_radar/export.py`) — the brain→arms seam.
- **Next step:** v1 — have Demand Radar trigger a Kami campaign directly from the export
  (or contribute a "Demand Radar import" PR to Kami); then v2 — the `conversion:` feedback source.
