# Job Prepper

An agentic tool that matches a job description against your resume,
surfaces the ATS keywords you're missing, and generates a tailored,
fact-checked resume plus interview prep — then tracks each role through
an application pipeline.

Find roles wherever you search (e.g. LinkedIn), then paste the JD or its
URL into Job Prepper.

## What it does

Paste in a job description and Job Prepper runs it through a LangGraph
pipeline: parses the JD, checks visa-sponsorship signals, tailors your
resume to the role, scores ATS keyword coverage, and evaluates the output
for relevance, factual accuracy, and keyword coverage — retrying the
tailoring step automatically if the evaluator flags a weak draft. The
result is a downloadable resume (DOCX), the list of matched and missing
ATS keywords, and interview prep talking points.

It also:

- **Screens before tailoring (optional)** — a fast Haiku check for
  location fit, dealbreakers (clearance requirements, staffing firms), and
  visa sponsorship before you spend on a full tailoring run.
- **Tracks a pipeline** of roles through stages (tailored → applied →
  responded → interviewing → offer), with funnel metrics.
- **Logs cost and token usage** per agent per run.

## How it works

The system is a set of specialized agents orchestrated two ways:

- **`graph.py`** — a LangGraph state machine that drives the core
  JD-to-resume pipeline (`parse_jd → visa_check → resume_agent →
  ats_agent → evaluator`, with a conditional retry edge back into
  `resume_agent` when the evaluator scores a draft too low).
- **`agents/`** — individual agents: screening, evaluation, resume
  tailoring, ATS scoring, and interview prep.
- **`tools/`** — supporting infrastructure: JD fetching/parsing, RAG retrieval over the career corpus, DOCX export,
  opportunity storage, visa-sponsorship detection, and usage/cost logging.

The Streamlit frontend (`app.py`) ties these together into three views:
Run Job Prepper (the tailoring pipeline), Pipeline (application tracking),
and Usage (cost/token tracking).

The app is password-gated (`APP_PASSWORD` via Streamlit secrets or `.env`)
since it runs on the owner's API keys.

## Tech stack

Streamlit · LangGraph · Anthropic API (Claude Sonnet + Haiku) · ChromaDB + sentence-transformers (RAG) · Supabase (persistence) · Tavily (web search) · python-docx (resume export)

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
| `SUPABASE_URL` / `SUPABASE_KEY` | Opportunity + history persistence |
| `TAVILY_API_KEY` | Web search for visa/company research |

> **Note:** `resume.txt` uses `[PHONE]` and `[EMAIL]` placeholders. Real
> values are only substituted at display/export time via `CONTACT_PHONE`
> and `CONTACT_EMAIL` — never stored in the corpus.

## Project structure

```
app.py                        Streamlit frontend: Run, Pipeline, Usage pages
graph.py                      LangGraph pipeline: JD → visa check → resume → ATS → evaluation (with retry)
resume.txt                    Source resume (contact info uses placeholders)
config/
  screening.yaml              Location allowlist, dealbreaker keywords, staffing firm signals
agents/
  screening_agent.py          Fast pre-screen (location, dealbreakers, visa, fit)
  resume_agent.py             Tailors resume to a specific JD
  ats_agent.py                Scores ATS keyword coverage
  evaluator.py                Scores resume quality, triggers retries
  prep_agent.py               Generates interview prep talking points
tools/
  jd_fetcher.py               Fetches JD from URL (SSRF-safe: blocks private IPs and non-http schemes)
  jd_parser.py                Extracts structured fields from JD text
  resume_retriever.py         RAG retrieval over the career corpus (ChromaDB)
  opportunity_store.py        Pipeline/funnel persistence (Supabase)
  visa_check.py               Visa sponsorship signal detection
  docx_export.py              Resume → DOCX export
  usage_logger.py             Per-agent token and cost tracking (SQLite)
scripts/
  migrate_history.py          One-off data migration
career_corpus/                ChromaDB corpus (resume.txt; factual content only)
```
