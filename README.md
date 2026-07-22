# Job Prepper

An agentic job-search system that turns a job description into a tailored,
ATS-checked resume and interview prep — while also tracking every
opportunity through a search → screen → tailor → apply funnel.

## What it does

Paste in a job description and Job Prepper runs it through a LangGraph
pipeline: parses the JD, checks visa-sponsorship signals, tailors your
resume to the role, scores ATS keyword coverage, and evaluates the output
for quality — retrying the tailoring step automatically if the evaluator
flags a weak draft. The result is an approved, downloadable resume (DOCX)
plus a set of interview prep talking points.

Beyond one-off runs, Job Prepper also:

- **Discovers roles** across multiple job search APIs (SerpAPI, Adzuna,
  Remotive) in parallel and suggests new title variants to search based on
  which titles have historically converted.
- **Screens before tailoring** — a fast Haiku-powered screening agent runs
  first, checking location fit, dealbreaker keywords (clearance
  requirements, staffing firms), and visa sponsorship signals, so the
  more expensive tailoring step only runs on promising matches.
- **Tracks a pipeline** of opportunities through stages (discovered →
  screened in → tailored → applied → responded → interviewing → offer),
  with funnel metrics.
- **Runs on a schedule** — a GitHub Actions workflow triggers daily
  discovery on weekday mornings, so new matches are waiting when you check
  in.
- **Logs cost and token usage** per agent per run, so the tool is
  instrumented, not a black box.

## How it works

The system is a set of specialized agents orchestrated two ways:

- **`graph.py`** — a LangGraph state machine that drives the core
  JD-to-resume pipeline (`parse_jd → visa_check → resume_agent →
  ats_agent → evaluator`, with a conditional retry edge back into
  `resume_agent` when the evaluator scores a draft too low).
- **`agents/`** — individual agents: title discovery, screening,
  evaluation, resume tailoring, ATS scoring, and interview prep.
- **`tools/`** — supporting infrastructure: multi-provider job search,
  JD fetching/parsing, RAG retrieval over the career corpus, DOCX export,
  opportunity storage, visa-sponsorship detection, and usage/cost logging.

The Streamlit frontend (`app.py`) ties these together into four views: Job
Search (discovery), Run Job Prepper (the tailoring pipeline), Pipeline
(funnel tracking), and Usage (cost/token tracking).

The app is password-gated (`APP_PASSWORD` via Streamlit secrets or `.env`)
since it runs on the owner's API keys.

## Tech stack

Streamlit · LangGraph · Anthropic API (Claude Sonnet + Haiku) · ChromaDB + sentence-transformers (RAG) · Supabase (persistence) · SerpAPI / Adzuna / Remotive (job search) · Tavily (web search) · python-docx (resume export)

## Running it locally

```bash
pip install -r requirements.txt
cp .env.example .env   # add your keys — see table below
streamlit run app.py
```

Required environment variables / Streamlit secrets:

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Powers all agents |
| `APP_PASSWORD` | Gates access to the app |
| `CONTACT_PHONE` / `CONTACT_EMAIL` | Real contact info, substituted at export time only |
| `SERPAPI_KEY` | Job search via Google (optional — Remotive works with no key) |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Adzuna job search (optional — free at developer.adzuna.com) |
| `SUPABASE_URL` / `SUPABASE_KEY` | Opportunity + history persistence |
| `TAVILY_API_KEY` | Web search for visa/company research |

> **Note:** `resume.txt` uses `[PHONE]` and `[EMAIL]` placeholders. Real
> values are only substituted at display/export time via `CONTACT_PHONE`
> and `CONTACT_EMAIL` — never stored in the corpus.

## Scheduled discovery

`.github/workflows/daily_discovery.yml` runs `scripts/daily_discovery.py`
on weekday mornings (7am ET) via GitHub Actions, using the lighter
`requirements-discovery.txt` dependency set. Configure the same secrets
above as repository secrets to enable it.

## Project structure

```
app.py                        Streamlit frontend: Job Search, Run, Pipeline, Usage pages
graph.py                      LangGraph pipeline: JD → visa check → resume → ATS → evaluation (with retry)
resume.txt                    Source resume (contact info uses placeholders)
config/
  screening.yaml              Location allowlist, dealbreaker keywords, staffing firm signals
agents/
  title_discovery_agent.py    Suggests new job title variants to search
  screening_agent.py          Fast pre-screen (location, dealbreakers, visa, fit)
  resume_agent.py             Tailors resume to a specific JD
  ats_agent.py                Scores ATS keyword coverage
  evaluator.py                Scores resume quality, triggers retries
  prep_agent.py               Generates interview prep talking points
tools/
  job_search.py               Multi-provider job search (SerpAPI / Adzuna / Remotive), parallel + dedup
  jd_fetcher.py               Fetches JD from URL (SSRF-safe: blocks private IPs and non-http schemes)
  jd_parser.py                Extracts structured fields from JD text
  resume_retriever.py         RAG retrieval over the career corpus (ChromaDB)
  opportunity_store.py        Pipeline/funnel persistence (Supabase)
  visa_check.py               Visa sponsorship signal detection
  docx_export.py              Resume → DOCX export
  usage_logger.py             Per-agent token and cost tracking (SQLite)
scripts/
  daily_discovery.py          Scheduled discovery entry point (headless, no Streamlit)
career_corpus/                ChromaDB corpus (resume.txt; factual content only)
.github/workflows/
  daily_discovery.yml         Weekday 7am ET cron + manual dispatch
```
