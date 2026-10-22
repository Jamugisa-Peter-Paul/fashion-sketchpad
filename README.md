# Fashion Sketchpad

Draw or photograph a garment sketch, tap a few choices, and get photoreal front and back renders from the
self-hosted ComfyUI server.

- `gateway/`: FastAPI service that runs next to ComfyUI on the server
- `app/`: Next.js + Capacitor mobile app (Android first)
- `docs/`: [Architecture](docs/ARCHITECTURE.md), [Deploying the gateway](docs/DEPLOY.md)
- `deploy/`: systemd unit and smoke-test script

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

### Without the GPU server

`gateway.tools.fake_comfy` mimics ComfyUI's API, so you can run the whole flow on Windows. Its
"renders" are your cleaned lines tinted in the chosen colour.

```powershell
# terminal 1
.venv\Scripts\python -m gateway.tools.fake_comfy --port 8188 --seconds 5
# terminal 2 (COMFY_URL=http://127.0.0.1:8188 in gateway\.env)
.venv\Scripts\python -m uvicorn gateway.main:create_app --factory --env-file gateway\.env --port 8190 --reload
```

### Preview sketch cleaning

```powershell
.venv\Scripts\python -m gateway.tools.clean gateway\tests\samples\shirt_front_paper.jpeg
# -> gateway\tools\out\shirt_front_paper_{lines,control,check}.png
```
