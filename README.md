# Semantic Job Matching System

An intelligent resume-to-job matching system powered by a **five-dimension scoring engine** and AI explanations. The system parses PDF/DOCX resumes, scores candidates against job postings across five weighted dimensions, and generates natural-language explanations via Moonshot Kimi.

## Features

- **Five-Dimension Scoring**: Weighted ensemble of semantic similarity, skill graph, seniority, culture/values, and salary fit
- **PDF/DOCX Resume Parsing**: Extracts structured candidate data (skills, seniority, salary expectation, culture keywords) via LLM
- **Skill Graph Matching**: NetworkX-based graph traversal for ecosystem-aware skill similarity
- **Culture & Values Matching**: Independent MiniLM embedding space for culture signal words
- **AI-Powered Explanations**: Moonshot Kimi generates match reasons and skill gap analysis
- **RESTful API**: FastAPI with async request handling and CORS support
- **Non-blocking Inference**: PyTorch model calls run in `ThreadPoolExecutor` to avoid event-loop deadlock

## Scoring Dimensions

| Dimension | Weight | Method |
|-----------|--------|--------|
| Semantic Match | 30% | `all-mpnet-base-v2` + cosine similarity |
| Skill Graph Match | 25% | NetworkX graph hop-based overlap |
| Seniority Match | 20% | Rule engine (SENIORITY_HIERARCHY) |
| Culture / Values Match | 15% | `all-MiniLM-L6-v2` + culture dimension vectors |
| Salary Match | 10% | Interval overlap rule engine |

## Architecture

```
semantic-job-match-ml/
├── data/
│   ├── jobs/
│   │   └── job_mock.json          # Job listings
│   ├── indices/                   # FAISS index files (legacy)
│   └── tests/
│       └── test_resumes.json
├── src/
│   ├── api/
│   │   ├── main.py                # FastAPI app, CORS, startup pre-warm
│   │   └── routes.py              # API endpoints (5-dim + legacy)
│   ├── core/
│   │   ├── config.py              # Env config (Moonshot API key/model)
│   │   ├── match_config.py        # SENIORITY_HIERARCHY, TECH_ECOSYSTEMS,
│   │   │                          # FIVE_DIM_WEIGHTS, CULTURE_DIMENSIONS
│   │   ├── five_dim_scorer.py     # Main scoring orchestrator
│   │   └── nltk_init.py           # NLTK data bootstrap
│   ├── dimensions/
│   │   ├── semantic_matcher.py    # Dimension 1 – MPNet cosine similarity
│   │   ├── skill_graph_matcher.py # Dimension 2 – NetworkX graph walk
│   │   ├── seniority_matcher.py   # Dimension 3 – rule engine
│   │   ├── culture_matcher.py     # Dimension 4 – MiniLM culture vectors
│   │   └── salary_matcher.py      # Dimension 5 – interval overlap
│   ├── models/
│   │   ├── embedder.py            # SentenceTransformer wrapper (legacy)
│   │   ├── matcher.py             # FAISS matcher (legacy /org endpoints)
│   │   └── schemas.py             # Pydantic models (CandidateProfile,
│   │                              # JobPosting, FiveDimScore, SalaryRange…)
│   └── services/
│       ├── job_loader.py          # Load jobs from data/jobs/job_mock.json
│       ├── job_adapter.py         # dict → JobPosting conversion
│       ├── build_candidate_profile.py  # parsed dict → CandidateProfile
│       ├── resume_parser.py       # pdfplumber + Moonshot structured parse
│       └── llm_explainer_service.py    # AsyncOpenAI → Moonshot explanations
└── scripts/
    ├── build_faiss_index.py       # Build FAISS index (legacy)
    ├── query_match.py
    ├── download_nltk_data.py
    └── run_server.py              # Start uvicorn server
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

The server starts at `http://127.0.0.1:8000`. On startup it pre-warms the `FiveDimScorer` (loads both PyTorch models) in a worker thread — you will see:

```
[startup] Pre-warming FiveDimScorer in executor thread...
[startup] FiveDimScorer pre-warm complete.
```

Swagger UI: `http://127.0.0.1:8000/docs`

### 2. API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/match_resume_file` | **Primary** – Upload PDF/DOCX, 5-dim scoring + LLM explanation |
| POST | `/api/match_resume` | Text input, 5-dim scoring + LLM explanation |
| POST | `/api/match_resume_file_org` | Legacy – File upload, FAISS semantic only |
| POST | `/api/match_resume_org` | Legacy – Text input, FAISS semantic only |

### 3. Upload Resume File (Primary Endpoint)

```bash
curl -X POST http://127.0.0.1:8000/api/match_resume_file \
  -F "file=@resume.pdf" \
  -F "top_k=5"
```

**Response Example**

```json
{
  "matches": [
    {
      "job_id": "3",
      "job_title": "Backend Engineer - Python",
      "company": "TechCorp",
      "score": 0.81,
      "five_dim_score": {
        "semantic":   { "score": 0.87, "weight": 0.30, "weighted_score": 0.261 },
        "skill_graph":{ "score": 0.75, "weight": 0.25, "weighted_score": 0.188 },
        "seniority":  { "score": 0.90, "weight": 0.20, "weighted_score": 0.180 },
        "culture":    { "score": 0.72, "weight": 0.15, "weighted_score": 0.108 },
        "salary":     { "score": 0.80, "weight": 0.10, "weighted_score": 0.080 }
      },
      "why_match": [
        "Strong Python + FastAPI background aligns with core stack.",
        "Senior-level seniority matches the role requirement."
      ],
      "skill_gaps": [
        "Kubernetes experience not evidenced in resume.",
        "PostgreSQL tuning skills recommended."
      ]
    }
  ]
}
```

### 4. Text-Based Match

```bash
curl -X POST http://127.0.0.1:8000/api/match_resume \
  -H "Content-Type: application/json" \
  -d '{"resume_text": "Python developer with 3 years FastAPI experience", "top_k": 5}'
```

## How It Works

### Resume Parsing Flow
1. `pdfplumber` extracts raw text from the uploaded PDF/DOCX
2. Moonshot Kimi (sync `OpenAI` client) parses the text into structured JSON: skills list, seniority level, expected salary range, culture keywords, years of experience
3. `build_candidate_profile()` converts the parsed output into a `CandidateProfile` Pydantic model

### Five-Dimension Scoring Flow
1. `FiveDimScorer.score_batch()` iterates over all `JobPosting` objects sequentially (no `ThreadPoolExecutor` internally — avoids PyTorch OMP deadlock)
2. Each dimension scorer returns a `DimensionScore` with `score`, `weight`, `weighted_score`, and `details`
3. `FiveDimScore.compute_final()` sums weighted scores into `final_score`
4. Results are sorted by `final_score` and the top-k are returned

### LLM Explanation Flow
1. `explain_match_loop()` calls Moonshot Kimi via `AsyncOpenAI` (non-blocking)
2. `asyncio.gather()` runs all top-k explanations concurrently
3. Each explanation includes `why_match` (bullet reasons) and `skill_gaps`

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

No index rebuild needed — jobs are loaded from JSON at request time.

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
- Current config uses `allow_credentials=False` — do not change `allow_origins` to a specific domain unless you also set `allow_credentials=True`

## Performance

- **Startup pre-warm**: ~5–10s (model download on first run; cached thereafter)
- **Scoring latency**: ~200–500ms for 20 jobs (sequential, CPU)
- **LLM explanation**: ~2–4s per job (concurrent via `asyncio.gather`)
- **Total API response**: ~3–8s end-to-end for top-3 results

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