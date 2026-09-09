# DRiskify (NIVETA Platform) — Base44 Dev Environment

## Architecture
- **Frontend**: React 18 + Vite (port 3000), proxies `/api` to the backend
- **Backend**: FastAPI / uvicorn (port 8000, internal), serves `/api/*` endpoints
- Single-origin wiring: only port 3000 is public; all API calls go through the Vite proxy

## Running
```bash
docker compose -f docker-compose.base44.yml up -d
```

## Secrets
- `GROQ_API_KEY` — Groq API key (console.groq.com/keys). Required for LLM synthesis.
- `SERPER_API_KEY` — Serper API key (serper.dev). Required for web search / scraping.
- Both are optional for boot (the app starts without them) but needed for vendor analysis to function.
- The AI engine has a fallback chain: Gemini → Groq → OpenAI — any one AI key enables synthesis.

## Notes
- Vite proxy target is configurable via `VITE_API_PROXY_TARGET` (defaults to `http://localhost:8000`; set to `http://backend:8000` in compose).
- Backend uses `python-dotenv` with `override=False`, so compose `env_file` values take precedence over any `.env`.
- `vite.config.js` uses `allowedHosts: true` to accept the preview's external hostname.
