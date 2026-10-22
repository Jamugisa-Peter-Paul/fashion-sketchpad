# Fashion Sketchpad

Draw or photograph a garment sketch, tap a few choices, and get photoreal front and back renders from the
self-hosted ComfyUI server.

- `gateway/`: FastAPI service that runs next to ComfyUI on the server
- `app/`: Next.js + Capacitor mobile app (Android first)
- `docs/`: [Architecture](docs/ARCHITECTURE.md)

## Gateway: local development (Windows, Python 3.12+)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r gateway\requirements-dev.txt
.venv\Scripts\python -m pytest
copy gateway\.env.example gateway\.env   # then edit TEMPLATES_DIR, DATA_DIR, APP_TOKENS
.venv\Scripts\python -m uvicorn gateway.main:create_app --factory --env-file gateway\.env --port 8190 --reload
```

Check it:

```powershell
curl http://127.0.0.1:8190/api/health
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8190/api/catalog
```
