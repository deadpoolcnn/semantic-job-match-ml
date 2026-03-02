# Semantic Job Matching System

An intelligent resume-to-job matching system powered by a **multi-agent pipeline** and a **five-dimension scoring engine**. The system orchestrates five specialist agents across a three-phase DAG, parses PDF/DOCX resumes, scores candidates against job postings across five weighted dimensions, predicts career trajectories, and generates rich natural-language insights via Moonshot Kimi.

## Features

- **Multi-Agent Architecture**: Six specialist agents coordinated by an Orchestrator in a 3-phase DAG (parse + analyze → score + predict + counterfactual → insight + matrix)
- **Five-Dimension Scoring**: Weighted ensemble of semantic similarity, skill graph, seniority, culture/values, and salary fit
- **JD Analysis Cache**: LLM-powered JD enrichment cached by file mtime — zero re-analysis cost on repeated requests
- **Career Path Prediction**: Job-agnostic 5-year trajectory with milestones and skill gap analysis
- **Counterfactual Career Paths**: Per-job "what if you take this role" trajectory with `DecisionGate` fork points (IC vs management, etc.) and key risks
- **Job Comparison Matrix**: Cross-job analysis across 6 career dimensions (career ceiling, technical depth, risk, salary trajectory, culture & pace) with a final recommendation
- **PDF/DOCX Resume Parsing**: Extracts structured candidate data (skills, education, seniority, salary, culture keywords) via LLM
- **Skill Graph Matching**: NetworkX-based graph traversal for ecosystem-aware skill similarity
- **Culture & Values Matching**: Independent MiniLM embedding space for culture signal words
- **AI-Powered Insights**: Per-job `why_match`, `skill_gaps`, `career_fit_commentary` + overall candidacy summary and development plan
- **RESTful API**: FastAPI with async request handling, CORS support, and per-agent timing in responses
- **Non-blocking Inference**: PyTorch model calls run in `ThreadPoolExecutor` to avoid event-loop deadlock

## Scoring Dimensions

| Dimension | Weight | Method |
|-----------|--------|--------|
| Semantic Match | 30% | `all-mpnet-base-v2` + cosine similarity |
| Skill Graph Match | 25% | NetworkX graph hop-based overlap |
| Seniority Match | 20% | Rule engine (SENIORITY_HIERARCHY) |
| Culture / Values Match | 15% | `all-MiniLM-L6-v2` + culture dimension vectors |
| Salary Match | 10% | Interval overlap rule engine |

## Multi-Agent Architecture

### Why Multi-Agent?

The system is structured as a multi-agent pipeline rather than a flat function chain for three concrete reasons:

1. **New capabilities requiring independent LLM calls**: `JobAnalyzerAgent` (JD implicit requirement extraction) and `CareerPathPredictorAgent` (5-year trajectory) are entirely new features that don't fit into the existing scoring flow
2. **JD result caching**: `JobAnalyzerAgent` holds a process-level mtime cache — analyzed JDs are reused across requests without re-calling the LLM
3. **Error isolation**: Each agent captures its own failures into `ctx.errors`; the pipeline degrades gracefully instead of returning a 500

### Agent Roles

| Agent | Phase | Responsibility |
|-------|-------|---------------|
| `ResumeParserAgent` | 1 | PDF/DOCX text extraction + Moonshot structured parse → `ResumeProfile` |
| `JobAnalyzerAgent` | 1 | LLM extraction of implicit requirements + culture signals per JD (cached) → `AnalyzedJob[]` |
| `MatchScorerAgent` | 2 | Five-dimension batch scoring → `FiveDimScore[]` |
| `CareerPathPredictorAgent` | 2 | Job-agnostic 5-year trajectory prediction → `CareerPrediction` |
| `CounterfactualCareerAgent` | 2 | Per-job "what if you take this role" path with `DecisionGate` forks + risks → `JobCareerPath[]` |
| `InsightGeneratorAgent` | 3 | Per-job insights + comparison matrix + overall summary → `InsightReport` |

### Execution DAG

```
Request
  │
  ├─── Phase 1 (asyncio.gather) ──────────────────────────────────────────────┐
  │         │                                                                   │
  │   ResumeParserAgent                                           JobAnalyzerAgent
  │   pdfplumber + Moonshot (sync → executor)                     Moonshot async × N JDs
  │   → ctx.candidate_profile                                     (cache hit → 0ms)
  │                                                               → ctx.analyzed_jobs
  │
  ├─── Phase 2 (asyncio.gather, waits for Phase 1) ───────────────────────────┐
  │         │                          │                                        │
  │   MatchScorerAgent      CareerPathPredictorAgent          CounterfactualCareerAgent
  │   FiveDimScorer          Moonshot (single call)           Moonshot × N JDs (concurrent)
  │   (→ executor)           job-agnostic 5-yr path           per-job path + DecisionGates
  │   → scored_results       → career_prediction              → job_career_paths
  │
  └─── Phase 3 (serial, waits for Phase 2) ──────────────────────────────────
             │
       InsightGeneratorAgent
       Phase A: per-job Moonshot calls (asyncio.gather)
               → why_match, skill_gaps, career_fit_commentary, counterfactual_path
       Phase B: one Moonshot call → overall_summary, development_plan
       Phase C: one Moonshot call → job_comparison_matrix (6-dimension cross-job table)
       → ctx.insight_report
```

### Error Isolation

Every agent is wrapped by `AgentBase.__call__`, which:
- Records wall-clock elapsed time into `ctx.timings[agent_name]`
- Catches any exception into `ctx.errors[agent_name]` (non-fatal)
- Enforces per-agent `timeout` (default 60s, overridden per agent)

The `OrchestratorAgent` has additional hard-dependency logic:
- `ResumeParserAgent` failure → abort (nothing to score)
- `JobAnalyzerAgent` failure → fallback to unenriched `JobPosting` objects, scoring continues
- `MatchScorerAgent` failure → abort Phase 3 (nothing to explain)
- `CareerPathPredictorAgent` failure → insight proceeds without generic career context
- `CounterfactualCareerAgent` failure → **non-fatal**; per-job paths omitted, comparison matrix skips trajectory data

### JD Cache

`JobAnalyzerAgent` maintains a process-level in-memory cache:

```
_cache = {
  "mtime": float,               # last modified time of job_mock.json
  "results": dict[job_id, AnalyzedJob]
}
```

- **Cold start**: analyzes all JDs concurrently via `asyncio.gather`, then stores results
- **Cache hit**: mtime unchanged → returns cached results, zero LLM calls
- **Invalidation**: mtime changed (file updated) → clears and re-analyzes
- **Pre-warm**: called at server startup alongside `FiveDimScorer` pre-warm

## Architecture

```
semantic-job-match-ml/
├── data/
│   ├── jobs/
│   │   └── job_mock.json              # Job listings
│   ├── indices/                       # FAISS index files (legacy)
│   └── tests/
│       └── test_resumes.json
├── src/
│   ├── agents/                        # ── Multi-agent layer ──
│   │   ├── base.py                    # AgentBase, AgentContext (shared state)
│   │   ├── orchestrator.py            # 3-phase DAG coordinator
│   │   ├── resume_parser_agent.py     # Phase 1: parse PDF → ResumeProfile
│   │   ├── job_analyzer_agent.py      # Phase 1: LLM JD analysis + mtime cache
│   │   ├── match_scorer_agent.py      # Phase 2: FiveDimScorer wrapper
│   │   ├── career_path_predictor_agent.py       # Phase 2: job-agnostic 5-yr trajectory
│   │   ├── counterfactual_career_agent.py       # Phase 2: per-job paths + DecisionGates
│   │   └── insight_generator_agent.py # Phase 3: insights + comparison matrix
│   ├── api/
│   │   ├── main.py                    # FastAPI app, CORS, startup pre-warm
│   │   ├── routes.py                  # V1 endpoints (5-dim, legacy)
│   │   └── routes_v2.py               # V2 endpoints (multi-agent pipeline)
│   ├── core/
│   │   ├── config.py                  # Env config (Moonshot API key/model)
│   │   ├── match_config.py            # SENIORITY_HIERARCHY, TECH_ECOSYSTEMS,
│   │   │                              # FIVE_DIM_WEIGHTS, CULTURE_DIMENSIONS
│   │   ├── five_dim_scorer.py         # Main scoring orchestrator
│   │   └── nltk_init.py               # NLTK data bootstrap
│   ├── dimensions/
│   │   ├── semantic_matcher.py        # Dimension 1 – MPNet cosine similarity
│   │   ├── skill_graph_matcher.py     # Dimension 2 – NetworkX graph walk
│   │   ├── seniority_matcher.py       # Dimension 3 – rule engine
│   │   ├── culture_matcher.py         # Dimension 4 – MiniLM culture vectors
│   │   └── salary_matcher.py          # Dimension 5 – interval overlap
│   ├── models/
│   │   ├── schemas.py                 # CandidateProfile, JobPosting,
│   │   │                              # FiveDimScore, SalaryRange…
│   │   └── agent_schemas.py           # ResumeProfile, AnalyzedJob, CareerPrediction,
│   │                                  # JobCareerPath, DecisionGate, Milestone,
│   │                                  # JobInsight, InsightReport, JobComparisonMatrix…
│   └── services/
│       ├── job_loader.py              # Load jobs from data/jobs/job_mock.json
│       ├── job_adapter.py             # dict → JobPosting conversion
│       ├── build_candidate_profile.py # parsed dict → CandidateProfile (V1)
│       ├── resume_parser.py           # pdfplumber + Moonshot structured parse
│       └── llm_explainer_service.py   # AsyncOpenAI → Moonshot explanations (V1)
└── scripts/
    ├── build_faiss_index.py           # Build FAISS index (legacy only)
    ├── query_match.py
    ├── download_nltk_data.py
    └── run_server.py                  # Start uvicorn server
```

## Prerequisites

- Python 3.10+
- Moonshot Kimi API Key (get from [Moonshot Platform](https://platform.moonshot.ai/))

## Installation

1. **Clone the repository**

```bash
git clone <repository-url>
cd semantic-job-match-ml
```

2. **Create virtual environment**

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Set up environment variables**

Create a `.env` file in the project root:

```env
MOONSHOT_API_KEY=sk-your_moonshot_api_key_here
MOONSHOT_MODEL=kimi-k2.5
```

## Usage

### 1. Start the API Server

```bash
PYTHONPATH=. python scripts/run_server.py
```

The server starts at `http://127.0.0.1:8000`. On startup it concurrently pre-warms:
- `FiveDimScorer` (PyTorch models) in executor thread
- `JobAnalyzerAgent` JD cache (Moonshot LLM analysis of all JDs)

```
[startup] Pre-warming FiveDimScorer + JD cache...
[startup] Pre-warm complete.
```

Swagger UI: `http://127.0.0.1:8000/docs`

### 2. API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v2/match_resume_file` | **Primary** – Multi-agent pipeline, full insight report |
| POST | `/api/match_resume_file` | V1 – 5-dim scoring + LLM explanation |
| POST | `/api/match_resume` | V1 – Text input, 5-dim scoring + LLM explanation |
| POST | `/api/match_resume_file_org` | Legacy – FAISS semantic only |
| POST | `/api/match_resume_org` | Legacy – Text input, FAISS semantic only |
| GET | `/api/v2/jd_cache/status` | Inspect JD cache state |
| DELETE | `/api/v2/jd_cache` | Force-invalidate JD cache |

### 3. V2 Multi-Agent Endpoint (Primary)

```bash
curl -X POST http://127.0.0.1:8000/api/v2/match_resume_file \
  -F "file=@resume.pdf" \
  -F "top_k=3"
```

**Response Example**

```json
{
  "request_id": "20260226_173000_123456",
  "candidate_summary": {
    "name": "Alex Chen",
    "current_title": "Backend Engineer",
    "seniority": "senior",
    "years_of_experience": 5.0,
    "skills": ["Python", "FastAPI", "Docker", "PostgreSQL"],
    "career_objective": "Seeking a staff engineer role in platform or infrastructure."
  },
  "career_prediction": {
    "current_level": "senior",
    "target_role_in_5yr": "Staff Engineer",
    "milestones": [
      {"year": 1, "title": "Tech Lead", "skills_needed": ["system design", "mentoring"], "decision_gate": null},
      {
        "year": 3,
        "title": "Principal Engineer",
        "skills_needed": ["cross-team coordination"],
        "decision_gate": {
          "year": 3,
          "question": "Stay IC or move to Engineering Manager?",
          "option_A": "IC track → Staff Engineer, deep technical ownership",
          "option_B": "Management track → Engineering Manager, team of 6–8",
          "impact": "5-yr salary gap ~20–30%; IC gains tech depth, EM gains org influence"
        }
      },
      {"year": 5, "title": "Staff Engineer", "skills_needed": ["technical strategy"], "decision_gate": null}
    ],
    "skill_gaps_to_bridge": ["Kubernetes", "distributed systems"],
    "confidence_note": "High confidence based on strong technical progression."
  },
  "top_matches": [
    {
      "job_id": "3",
      "job_title": "Backend Engineer - Python",
      "company": "TechCorp",
      "score": 0.81,
      "five_dim_score": {
        "semantic":    {"score": 0.87, "weight": 0.30, "weighted_score": 0.261},
        "skill_graph": {"score": 0.75, "weight": 0.25, "weighted_score": 0.188},
        "seniority":   {"score": 0.90, "weight": 0.20, "weighted_score": 0.180},
        "culture":     {"score": 0.72, "weight": 0.15, "weighted_score": 0.108},
        "salary":      {"score": 0.80, "weight": 0.10, "weighted_score": 0.080}
      },
      "why_match": ["Strong Python + FastAPI background aligns with core stack."],
      "skill_gaps": ["Kubernetes experience not evidenced in resume."],
      "career_fit_commentary": "This role accelerates your path to Staff by offering infrastructure ownership.",
      "implicit_requirements": ["comfort with ambiguity", "self-starter in distributed teams"],
      "counterfactual_path": {
        "job_id": "3",
        "job_title": "Backend Engineer - Python",
        "company": "TechCorp",
        "trajectory_summary": "Y1: Senior SWE → Y3: Tech Lead → Y5: Staff Engineer",
        "milestones": [
          {"year": 1, "title": "Senior SWE", "skills_needed": ["codebase onboarding"], "decision_gate": null},
          {
            "year": 3,
            "title": "Tech Lead",
            "skills_needed": ["system design", "mentoring"],
            "decision_gate": {
              "year": 3,
              "question": "Accept people-management track?",
              "option_A": "IC → Staff Engineer at TechCorp in 2 more years",
              "option_B": "EM → Engineering Manager, team of 5–8, roadmap ownership",
              "impact": "EM earns ~15% more at year 5; IC retains deeper technical ownership"
            }
          },
          {"year": 5, "title": "Staff Engineer", "skills_needed": ["org-wide strategy"], "decision_gate": null}
        ],
        "key_risks": [
          "Promotion to Staff may require 3-4 yr tenure at TechCorp",
          "Tech stack depth limits cross-industry transferability"
        ]
      }
    }
  ],
  "overall_summary": "Strong backend candidate with clear platform engineering trajectory.",
  "development_plan": "Prioritize Kubernetes certification in year 1. Take on system design ownership to reach Tech Lead by year 2.",
  "job_comparison_matrix": {
    "rows": [
      {"dimension": "Career Ceiling",       "values": {"3": "Staff Engineer", "7": "VP Engineering"}},
      {"dimension": "Management vs IC",     "values": {"3": "IC-first, optional EM at Y3", "7": "Strong EM path from Y2"}},
      {"dimension": "Technical Depth",      "values": {"3": "High — platform infra ownership", "7": "Medium — broad-scope leadership"}},
      {"dimension": "Risk Level",           "values": {"3": "Low — established company", "7": "Medium — early-stage startup"}},
      {"dimension": "Salary Trajectory",    "values": {"3": "~$180k–$240k by Y5", "7": "~$150k base + equity upside"}},
      {"dimension": "Culture & Pace",       "values": {"3": "Structured, quarterly OKRs", "7": "Fast-paced, high autonomy"}}
    ],
    "recommendation": "Choose Job 3 for stable IC growth to Staff; choose Job 7 if you prioritise equity upside and early management exposure."
  },
  "errors": {},
  "timings": {
    "resume_parser": 4.21,
    "job_analyzer": 0.01,
    "match_scorer": 0.38,
    "career_predictor": 2.87,
    "counterfactual_career": 5.43,
    "insight_generator": 7.82
  }
}
```

### 4. V1 Upload Endpoint

```bash
curl -X POST http://127.0.0.1:8000/api/match_resume_file \
  -F "file=@resume.pdf" \
  -F "top_k=5"
```

### 5. Text-Based Match (V1)

```bash
curl -X POST http://127.0.0.1:8000/api/match_resume \
  -H "Content-Type: application/json" \
  -d '{"resume_text": "Python developer with 3 years FastAPI experience", "top_k": 5}'
```

## How It Works

### V2 Multi-Agent Flow

```
POST /api/v2/match_resume_file
  │
  ├─ Phase 1 (parallel)
  │    ├─ ResumeParserAgent
  │    │    pdfplumber extracts text → Moonshot parses into structured JSON
  │    │    → name, skills, education, seniority, salary, culture_keywords, soft_skills
  │    └─ JobAnalyzerAgent
  │         checks mtime cache → hit: 0ms / miss: Moonshot × N JDs concurrently
  │         → implicit_requirements, culture_fit_signals per JD
  │
  ├─ Phase 2 (parallel — 3 agents)
  │    ├─ MatchScorerAgent
  │    │    FiveDimScorer.score_batch() in executor (PyTorch off event loop)
  │    │    → semantic + skill_graph + seniority + culture + salary scores
  │    ├─ CareerPathPredictorAgent
  │    │    single Moonshot call with candidate profile
  │    │    → job-agnostic 5-year trajectory, milestones, skill gaps
  │    └─ CounterfactualCareerAgent
  │         one Moonshot call per AnalyzedJob (all concurrent)
  │         → per-job trajectory: Y1/Y3/Y5 titles, optional DecisionGate forks, key_risks
  │
  └─ Phase 3 (serial)
       InsightGeneratorAgent
       Phase A: per-job Moonshot calls (asyncio.gather)
               → why_match, skill_gaps, career_fit_commentary
               → attaches counterfactual_path from Phase 2 to each JobInsight
       Phase B: one Moonshot call → overall_summary, development_plan
       Phase C: one Moonshot call → job_comparison_matrix
               (6 dimensions: career ceiling, mgmt vs IC, tech depth, risk, salary, culture)
```

### V1 Flow (still active, unchanged)

```
POST /api/match_resume_file
  parse_resume_file (executor) → build_candidate_profile
  → FiveDimScorer.score_batch (executor)
  → explain_match_loop (AsyncOpenAI, concurrent)
  → MatchResponse
```

### Async Safety

All blocking operations run in a `ThreadPoolExecutor` via `run_in_executor`:
- `parse_resume_file()` — sync pdfplumber + sync OpenAI call
- `scorer.score_batch()` — PyTorch `model.encode()` calls

`torch.set_num_threads(1)` is set globally at startup to prevent OMP cross-thread deadlock.

## Adding Your Own Job Data

Edit `data/jobs/job_mock.json`:

```json
[
  {
    "job_id": "1",
    "job_title": "Software Engineer",
    "company": "Your Company",
    "location": "Remote",
    "description": "Job description here...",
    "requirements": ["Requirement 1", "Requirement 2"],
    "required_skills": ["Python", "FastAPI"],
    "nice_to_have": ["Docker", "Kubernetes"],
    "seniority": "mid",
    "salary_range": "$100k - $150k",
    "culture_keywords": ["collaborative", "fast-paced"],
    "posted_date": "2026-02-01"
  }
]
```

No index rebuild needed. Updating this file automatically invalidates the JD cache on the next request.

## Development

### Running Tests

```bash
pytest tests/
```

### Build Legacy FAISS Index (optional)

Only needed for the `/org` legacy endpoints:

```bash
PYTHONPATH=. python -m scripts.build_faiss_index
```

## Deployment

### Docker (Local)

```bash
# Build the image
docker build -t semantic-job-match .

# Run the container
docker run -d \
  --name semantic-job-match \
  --restart unless-stopped \
  -p 8000:8000 \
  -e MOONSHOT_API_KEY=your_key \
  -e MOONSHOT_MODEL=kimi-k2-turbo-preview \
  semantic-job-match

# Verify
curl http://localhost:8000/health
```

> **Note**: The first build downloads PyTorch (CPU-only), sentence-transformers models, and NLTK data — expect 10–20 minutes. Subsequent builds complete in 1–2 minutes thanks to Docker layer caching.

### CI/CD with GitHub Actions

Pushing to `main` or `master` automatically runs the following pipeline:

```
push to main/master
        │
        ▼  (only when these paths change)
        │  src/**  scripts/**  data/**
        │  requirements.txt  Dockerfile  .github/workflows/deploy.yml
        │
  ┌─────┴──────────────────────────────────────────────┐
  │ Job 1: Build & Push                                │
  │  ├─ Log in to GitHub Container Registry (ghcr.io) │
  │  ├─ Build Docker image (two-layer cache strategy)  │
  │  │    layer 1: GHA cache (7-day TTL)               │
  │  │    layer 2: registry cache (permanent fallback) │
  │  └─ Push → ghcr.io/<owner>/<repo>:latest          │
  └─────────────────────────────────────────────────────┘
        │
        ▼
  ┌─────┴──────────────────────────────────────────────┐
  │ Job 2: Deploy                                      │
  │  ├─ SSH into server                                │
  │  ├─ docker pull ghcr.io/...latest                  │
  │  ├─ Stop and remove old container                  │
  │  ├─ docker run (inject MOONSHOT_API_KEY)           │
  │  ├─ Prune dangling images                          │
  │  └─ curl /health to verify deployment              │
  └─────────────────────────────────────────────────────┘
```

#### GitHub Secrets

Add the following 4 secrets in **Settings → Secrets and variables → Actions**:

| Secret | Description |
|--------|-------------|
| `MOONSHOT_API_KEY` | Moonshot Kimi API key |
| `SERVER_HOST` | Server IP address or domain |
| `SERVER_USER` | SSH login username |
| `SSH_PRIVATE_KEY` | SSH private key (public key must be in server's `~/.ssh/authorized_keys`) |

> `GITHUB_TOKEN` is automatically provided by GitHub Actions — no manual setup needed.

#### Manual Trigger

Go to **Actions → Build and Deploy to Server → Run workflow** in your GitHub repository to trigger a deployment without pushing code.

#### Changes That Do NOT Trigger Deployment

The following file changes are ignored to avoid unnecessary rebuilds:

- `README.md` and other `*.md` docs
- `.env`, `.dockerignore`
- `tests/` directory

## Troubleshooting

### Server hangs after "FiveDimScorer ready."
- **Cause**: PyTorch OMP cross-thread deadlock — scorer initialized in event-loop thread but `encode()` runs in worker thread
- **Fix**: Already applied — `torch.set_num_threads(1)` + startup pre-warm via `run_in_executor`

### 401 Unauthorized from Moonshot
- Check `.env` for leading/trailing spaces in `MOONSHOT_API_KEY`
- `config.py` calls `.strip()` as a safeguard

### "No text extracted from resume"
- Ensure the uploaded file is a valid PDF or DOCX (not scanned image-only PDF)

### CORS errors from frontend
- `allow_credentials=True` combined with `allow_origins=["*"]` is invalid per W3C spec
- Current config uses `allow_credentials=False`

### `ValueError: Invalid format specifier` in resume_parser
- **Cause**: f-string with unescaped `{` `}` in the LLM prompt template
- **Fix**: All literal `{` `}` in f-strings must be written as `{{` `}}`

## Performance

| Stage | Timing | Notes |
|-------|--------|-------|
| Startup pre-warm | ~5–15s | Model download on first run; cached thereafter |
| ResumeParserAgent | ~3–8s | pdfplumber + one Moonshot call |
| JobAnalyzerAgent (cold) | ~3–8s per JD | N JDs × Moonshot, concurrent |
| JobAnalyzerAgent (warm) | ~0ms | mtime cache hit |
| MatchScorerAgent | ~200–500ms | Sequential PyTorch scoring, 20 jobs |
| CareerPathPredictorAgent | ~2–4s | One Moonshot call (job-agnostic) |
| CounterfactualCareerAgent | ~3–8s | N JDs × Moonshot concurrent; Phase 2 parallel |
| InsightGeneratorAgent | ~5–12s | top-k concurrent calls (Phase A) + summary (Phase B) + matrix (Phase C) |
| **V2 total (warm cache)** | **~10–25s** | Phase 2 now 3-way parallel; Phase 3 has extra matrix call |
| V1 total | ~3–8s | No career prediction or JD analysis |

## Tech Stack

- **Framework**: FastAPI + uvicorn
- **ML**: SentenceTransformers (`all-mpnet-base-v2`, `all-MiniLM-L6-v2`), FAISS (legacy)
- **Graph**: NetworkX
- **LLM**: Moonshot Kimi via OpenAI-compatible SDK (`AsyncOpenAI` + sync `OpenAI`)
- **PDF Parsing**: pdfplumber
- **Language**: Python 3.10+

## License

MIT License

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## Acknowledgments

- [SentenceTransformers](https://www.sbert.net/) for embedding models
- [FAISS](https://github.com/facebookresearch/faiss) for efficient vector search
- [Moonshot Kimi](https://platform.moonshot.ai/) for LLM explanations and resume parsing
- [NetworkX](https://networkx.org/) for skill graph computation