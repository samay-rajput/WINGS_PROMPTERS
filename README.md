# NAVIgit (WINGS_PROMPTERS)

AI-powered GitHub repository intelligence with:

- **M1** Folder structure explanation
- **M2** Entry point + execution flow analysis
- **M3** Dependency graph visualization
- **RAG chat** over indexed repository context (B1/B2/B3 modes)

## Tech Stack

- **Frontend:** Vanilla HTML, CSS, JS (`frontend/`)
- **Backend API:** FastAPI (`backend/`)
- **LLM Providers:** Gemini + Groq fallback
- **RAG Retrieval:** FAISS + LangChain

## Repository Layout

```text
frontend/                Static UI (NAVIgit)
backend/
  app/                   Analysis pipeline + API routes (/analyze, /chat)
  api/                   RAG routes (/rag/index, /rag/chat, /rag/status)
  services/              Embedding, ingestion, vector store, chat services
rag-backend/             Standalone RAG backend variant (optional)
```

## Quick Start

## 1) Backend Setup

```bash
cd backend
pip install -r requirements.txt
```

Create/update `backend/.env`:

```env
# Analysis backend
GEMINI_API_KEY_PRIMARY=your_key
GEMINI_API_KEY_SECONDARY=your_key
GROQ_API_KEY=your_key
GITHUB_TOKEN=your_token

# RAG backend (same process)
GEMINI_API_KEY_RAG=your_key
GROQ_API_KEY_RAG=your_key
GITHUB_TOKEN_RAG=your_token
```

Run API:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload
```

Health check:

```bash
GET http://localhost:5000/health
```

## 2) Frontend Setup

Serve `frontend/` on port `5500` (VS Code Live Server recommended).

- URL: `http://localhost:5500`
- Backend expected at: `http://localhost:5000`

## API Overview

## `POST /analyze`

Request:

```json
{
  "github_url": "https://github.com/owner/repo"
}
```

Response (normalized):

```json
{
  "m1_folder_explanation": {},
  "m2_entry_analysis": {
    "entry_file": "...",
    "execution_flow": []
  },
  "m3_dependency_graph": [
    { "source": "...", "target": "..." }
  ],
  "m3_architecture_summary": "..."
}
```

## `POST /chat`

Request:

```json
{
  "message": "Explain the startup flow",
  "repo_url": "owner/repo"
}
```

Response:

```json
{
  "reply": "..."
}
```

## `POST /rag/index`

Indexes repo for RAG chat:

```json
{
  "github_url": "https://github.com/owner/repo"
}
```

## `GET /rag/status`

Returns whether current repo is indexed.

## `POST /rag/chat`

Request:

```json
{
  "question": "What are critical files?",
  "mode": "B1"
}
```

Modes:

- `B1` Critical files
- `B2` Execution flow
- `B3` Architecture summary

## Troubleshooting

- **Analyze button shows backend error:** confirm backend is running on `:5000`.
- **CORS issues:** frontend should run on localhost/127.0.0.1; backend allows local dev origins.
- **GitHub rate limit:** provide valid `GITHUB_TOKEN` / `GITHUB_TOKEN_RAG`.
- **RAG not ready yet:** call `/rag/index`, or wait for `/rag/status` to become indexed.

## Security Notes

- Never commit real API keys/tokens.
- Rotate any keys previously exposed.
- Keep `.env` values local and secret.

## License

MIT (or project team license choice).

