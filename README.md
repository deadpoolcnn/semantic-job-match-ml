# Semantic Job Matching System

An intelligent resume-to-job matching system powered by semantic search and AI. This project uses sentence embeddings (SentenceTransformers), FAISS for efficient vector search, and Gemini AI to provide explainable job recommendations.

## Features

- **Semantic Matching**: Uses MPNet embeddings to understand the semantic similarity between resumes and job descriptions
- **Fast Vector Search**: FAISS-powered indexing for efficient nearest neighbor search
- **AI-Powered Explanations**: Gemini AI generates match reasons and skill gap analysis
- **RESTful API**: FastAPI-based REST API for easy integration
- **Multilingual Support**: Supports multiple languages with `paraphrase-multilingual-mpnet-base-v2` model

## Architecture

```
semantic-job-match-ml/
├── data/                      # Data directory
│   ├── job_mock.json         # Sample job listings
│   └── indices/              # FAISS index files (generated)
├── src/
│   ├── api/                  # FastAPI application
│   │   ├── main.py          # API entry point
│   │   └── routes.py        # API endpoints
│   ├── core/                 # Core configurations
│   │   └── config.py        # Environment config
│   ├── models/               # ML models
│   │   ├── embedder.py      # Text embedding with SentenceTransformer
│   │   └── matcher.py       # FAISS-based job matching
│   └── services/             # Business logic
│       └── llm_explainer_service.py  # Gemini AI explanations
└── scripts/
    ├── build_faiss_index.py  # Build FAISS index from job data
    └── run_server.py         # Start FastAPI server
```

## Prerequisites

- Python 3.10+
- Google Gemini API Key

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
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash-exp
```

Get your Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).

## Usage

### 1. Build FAISS Index

First, build the vector index from your job data:

```bash
python -m scripts.build_faiss_index
```

This will:
- Load job listings from `data/job_mock.json`
- Generate embeddings using SentenceTransformer
- Create FAISS index at `data/indices/jobs_faiss.index`
- Save job metadata to `data/indices/jobs_meta.json`

### 2. Start the API Server

```bash
python scripts/run_server.py
```

The server will start at `http://127.0.0.1:8000`

### 3. Make API Requests

**Match Resume to Jobs**

```bash
curl -X POST http://127.0.0.1:8000/api/match_resume \
  -H "Content-Type: application/json" \
  -d '{
    "resume_text": "Python developer with 3 years experience in FastAPI and React",
    "top_k": 5
  }'
```

**Response Example**

```json
{
  "matches": [
    {
      "job_id": "3",
      "job_title": "Backend Engineer - Python",
      "company": "TechCorp",
      "score": 0.89,
      "why_match": [
        "3+ years Python experience matches requirement",
        "FastAPI expertise aligns with tech stack"
      ],
      "skill_gaps": [
        "Could benefit from PostgreSQL experience",
        "Docker/Kubernetes knowledge recommended"
      ]
    }
  ]
}
```

### 4. API Documentation

Access interactive API docs at:
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## How It Works

### 1. **Embedding Generation**
- Uses `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` model
- Converts resume text and job descriptions into 768-dimensional vectors
- Vectors are L2-normalized for cosine similarity

### 2. **Vector Search**
- FAISS IndexFlatIP performs inner product search
- Returns top-k most similar jobs based on semantic similarity
- Scores range from 0 to 1 (higher = better match)

### 3. **AI Explanation**
- Gemini AI analyzes resume and job description
- Generates human-readable match reasons
- Identifies skill gaps and improvement areas

## Configuration

### Model Selection

Edit `src/models/embedder.py` to change the embedding model:

```python
MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"  # English only
# or
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"  # Multilingual
```

### FAISS Index Type

For larger datasets (>100k jobs), consider using approximate search:

```python
# In build_faiss_index.py
index = faiss.IndexIVFFlat(quantizer, dim, nlist=100)
index.train(embeddings)
index.add(embeddings)
```

## Adding Your Own Job Data

Edit `data/job_mock.json` with your job listings:

```json
[
  {
    "job_id": "1",
    "job_title": "Software Engineer",
    "company": "Your Company",
    "location": "Remote",
    "description": "Job description here...",
    "requirements": ["Requirement 1", "Requirement 2"],
    "skills": ["Python", "FastAPI", "React"],
    "salary_range": "$100k - $150k",
    "posted_date": "2026-02-01"
  }
]
```

Then rebuild the index:

```bash
python -m scripts.build_faiss_index
```

## Development

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black src/ scripts/
ruff check src/ scripts/
```

## Troubleshooting

### "FAISS index not found" Error

Run the index builder first:
```bash
python -m scripts.build_faiss_index
```

### "GEMINI_API_KEY not found" Error

Ensure `.env` file exists with valid API key:
```bash
echo "GEMINI_API_KEY=your_key_here" > .env
```

### High Memory Usage

For large datasets, use quantized FAISS indexes or reduce `top_k` value.

## Performance

- **Index Building**: ~10 jobs/second (depends on model)
- **Search Latency**: <50ms for 10k jobs (IndexFlatIP)
- **API Response Time**: 1-2s (including LLM explanation)

## Tech Stack

- **Framework**: FastAPI
- **ML**: SentenceTransformers, FAISS
- **AI**: Google Gemini AI
- **Language**: Python 3.10+

## License

MIT License

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## Acknowledgments

- [SentenceTransformers](https://www.sbert.net/) for embedding models
- [FAISS](https://github.com/facebookresearch/faiss) for efficient vector search
- [Google Gemini](https://ai.google.dev/) for AI-powered explanations