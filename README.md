# DataQuest Python Sandbox

FastAPI service that executes learner Python snippets for the DataQuest app.

## Endpoints

- `GET /health` — liveness probe.
- `POST /run` — `{ "code": "...", "timeout": 5, "datasets": [...] }`; returns stdout, stderr, error, duration and peak memory.

## Run locally

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Deployed on Render as a Python web service:

- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`
