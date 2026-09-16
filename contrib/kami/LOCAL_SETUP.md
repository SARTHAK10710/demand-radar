# Running Kami + Demand Radar together — local setup (Windows + Gemini)

A step-by-step, copy-paste guide to run **Kami Community Edition** locally with the **Hermes**
agent on **Gemini**, then drop in the **Demand Radar `demand_signal_mining` skill**.

> Two processes run side by side: **Hermes gateway** (the agent brain, on `127.0.0.1:8642`) and
> **Kami's Next.js web app** (`localhost:3000`). You bring a Gemini key + a free Supabase project.
>
> **Repo note:** Kami's own docs clone from `github.com/saranambiar/kami` — use that. (`kami-community`
> may be a mirror; confirm with the maintainer before opening a PR.)
> **Model note:** Kami's evals are tuned on OpenAI `gpt-5.4`. Gemini *runs* it fine; use `gpt-5.4`
> only if you later need their eval suite to score exactly as designed.

---

## 0. Prerequisites
- **Node.js 20+** and npm — https://nodejs.org
- **Git**
- A **Gemini API key** — https://aistudio.google.com/app/apikey
- A free **Supabase** project — https://supabase.com
- **Windows PowerShell** (native — avoid WSL `/mnt/c` for the app; Turbopack breaks there)

---

## 1. Install Hermes (the agent)
In PowerShell:
```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
```
This installs everything (uv, Python 3.11, Node, a portable Git Bash) under `%LOCALAPPDATA%\hermes`.
Then reload your shell and check:
```powershell
hermes --version
hermes doctor
```

## 2. Point Hermes at Gemini
Easiest — use the wizard and pick the **Gemini** provider + a model:
```powershell
hermes model
```
Or set it explicitly. First put your key in `%LOCALAPPDATA%\hermes\.env`:
```dotenv
GEMINI_API_KEY=your_gemini_key_here
```
Then:
```powershell
hermes config set model.provider gemini
hermes config set model.default gemini-3-flash     # or a stronger Gemini model for the agent brain
hermes config set agent.reasoning_effort none
```
Prove the brain works (chat once, then exit):
```powershell
hermes
```

## 3. Turn on the API server + start the gateway
Generate a long random secret for the API server (this is NOT your Gemini key):
```powershell
$apiKey = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$apiKey    # copy this — you'll paste it into web/.env.local too
hermes config set API_SERVER_ENABLED true
hermes config set API_SERVER_HOST 127.0.0.1
hermes config set API_SERVER_PORT 8642
hermes config set API_SERVER_KEY $apiKey
```
Start the gateway in its **own terminal** and leave it running:
```powershell
hermes gateway
```
Smoke test (second terminal — use `Invoke-RestMethod`, not `curl`):
```powershell
$apiKey = Read-Host "Paste the same API_SERVER_KEY"
Invoke-RestMethod http://127.0.0.1:8642/v1/chat/completions `
  -Method POST -Headers @{ Authorization = "Bearer $apiKey" } `
  -ContentType "application/json" `
  -Body '{"model":"gemini-3-flash","messages":[{"role":"user","content":"say hi"}]}'
```
Pass = a normal reply (`finish_reason: stop`).

## 4. Clone Kami + install
```powershell
git clone https://github.com/saranambiar/kami.git
cd kami\web
npm install
cd ..
```

## 5. Supabase — create project + run migrations
1. Create a project at supabase.com; grab the **Project URL** and the **service_role** key (Settings → API).
2. In the Supabase **SQL editor**, run these files from `web/supabase/migrations/` **in order**
   (**skip 006**):
   `001_init` → `002_crm` → `003_marketing` → `004_sales` → `005_connected_accounts_session`
   → `007_sales_segments` → `008_domain_truth` → `009_distribution_opportunities` → `010_agent_run_logs`

## 6. Configure the web app
```powershell
cd web
copy .env.example .env.local
```
Edit `web\.env.local` — required:
```dotenv
HERMES_GATEWAY_URL=http://127.0.0.1:8642/v1/chat/completions
HERMES_API_KEY=<the same API_SERVER_KEY from step 3>
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<Supabase service_role key>
```
```powershell
cd ..
```

## 7. Sync skills + readiness (from repo root)
```powershell
npm run sync:skills
npm run readiness
```

## 8. Run + verify
- **Terminal A** (already running): `hermes gateway`
- **Terminal B**:
  ```powershell
  cd web
  npm run dev
  # if Turbopack errors on Windows:  npx next dev --webpack
  ```
Open **http://localhost:3000**, then check
`http://localhost:3000/api/capabilities` shows `hermes: true`, `database: true`, `modelConfigured: true`.

## 9. Install the Demand Radar skill (the integration)
Copy our skill folder into Kami's `skills/`, then re-sync:
```powershell
# from the demand-radar repo, copy the skill into your kami clone:
xcopy /E /I "path\to\demand-radar\contrib\kami\skills\demand_signal_mining" ".\skills\demand_signal_mining"
npm run sync:skills
```

## 10. Test it
1. In Kami (localhost:3000): enter a **domain** you control → confirm the dossier (**That's us**).
2. Choose **Find customers**.
3. Watch whether the manager uses `demand_signal_mining` and whether `community_post` signals /
   demand-sized segments appear. **Approve before any send — Kami must never invent emails.**

---

## Troubleshooting (from Kami's SETUP.md)
| Symptom | Fix |
|---|---|
| `/api/capabilities` → `hermes: false` | Gateway running? `HERMES_GATEWAY_URL` + `HERMES_API_KEY` must match Hermes' `API_SERVER_KEY`. |
| `database: false` | Supabase URL + service_role key set? Migrations through `010`? |
| Marketing queue empty / SQL errors | Migration `009` applied? |
| No run logs | Migration `010` applied? |
| Turbopack / MODULE_UNPARSABLE | Native PowerShell + `npx next dev --webpack`; don't run the app from WSL `/mnt/c`. |
| Skill not used | Re-run `npm run sync:skills`; confirm Hermes skills path; the manager only loads skills relevant to the step. |
| Defender flags `uv.exe` | Known false positive — whitelist the `%LOCALAPPDATA%\hermes\bin` folder (see Hermes README). |

## Reality check
This is a real multi-hour setup (Hermes + Supabase are the heavy parts). Get **Kami running on its
own first** (steps 1–8), confirm `/api/capabilities` is green, *then* add the skill (step 9). And
remember: the skill is **instructions Hermes executes** with your Gemini model — the Demand Radar
Python tool stays as the standalone prototype / reference for the output shape.
