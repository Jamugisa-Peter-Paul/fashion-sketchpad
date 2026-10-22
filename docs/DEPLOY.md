# Deploying the gateway

The steps below install the gateway on the Precision 5860 (`10.4.18.27`, user `dct`) next to ComfyUI and
publish it as `https://fashion-api.ucu-dct.org` through the existing `coolify` Cloudflare tunnel.
Nothing here touches ComfyUI, llama-swap, Coolify or the attendance system.

| What | Where |
|---|---|
| Code | `/home/dct/fashion-sketchpad` |
| Python venv | `/home/dct/fashion-sketchpad/.venv` |
| Config (secrets) | `/etc/fashion-gateway.env` (root:dct, 640) |
| Data (designs, renders) | `/home/dct/fashion-data` |
| Service | `fashion-gateway` (systemd, user `dct`) on `127.0.0.1:8190` |
| Public URL | `https://fashion-api.ucu-dct.org`, via the tunnel to `http://localhost:8190` |

## 1. Copy the code to the server

From the repo on Windows (PowerShell), ship only what git tracks:

```powershell
git archive --format=tar.gz -o fashion-sketchpad.tar.gz HEAD
scp fashion-sketchpad.tar.gz dct@10.4.18.27:/home/dct/
```

On the server:

```bash
mkdir -p ~/fashion-sketchpad && tar -xzf ~/fashion-sketchpad.tar.gz -C ~/fashion-sketchpad
mkdir -p ~/fashion-data
```

(If you push the repo to GitHub instead, `git clone` into `~/fashion-sketchpad` and use `git pull` to update.)

## 2. Python environment

```bash
ss -ltn | grep -q ':8190 ' && echo "8190 is taken, pick another port" || echo "8190 is free"
python3 --version
sudo apt install -y python3-venv          # if `python3 -m venv` complains
cd ~/fashion-sketchpad
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r gateway/requirements.txt
```

The gateway needs Python 3.12 or newer. If pip starts compiling numpy or OpenCV from source because the
system Python is too new for the published wheels, use a 3.12 venv instead:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
~/.local/bin/uv venv --python 3.12 .venv && ~/.local/bin/uv pip install -p .venv -r gateway/requirements.txt
```

Optionally run the tests on the server (they use the fake ComfyUI, not the GPU):

```bash
.venv/bin/pip install pytest && .venv/bin/python -m pytest
```

## 3. Config

Generate a token for each phone or person (any of them is accepted):

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Create `/etc/fashion-gateway.env`:

```bash
sudo tee /etc/fashion-gateway.env >/dev/null <<'EOF'
COMFY_URL=http://127.0.0.1:8188
TEMPLATES_DIR=/home/dct/ComfyUI/output/templates
DATA_DIR=/home/dct/fashion-data
APP_TOKENS=<token-1>,<token-2>
PUBLIC_BASE_URL=https://fashion-api.ucu-dct.org
EOF
sudo chown root:dct /etc/fashion-gateway.env && sudo chmod 640 /etc/fashion-gateway.env
```

Optional render overrides (defaults are the proven recipe): `RENDER_STEPS=28`, `RENDER_GUIDANCE=3.5`,
`LINES_STRENGTH=0.85`, `LINES_END=0.85`, `DEPTH_STRENGTH=0.3` (0 turns off the body-shape ControlNet),
`DEPTH_END=0.4`, `VIEW_HINT=1`.

## 4. systemd service

```bash
sudo cp ~/fashion-sketchpad/deploy/fashion-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fashion-gateway
systemctl status fashion-gateway --no-pager
journalctl -u fashion-gateway -f            # logs
```

Local checks on the server:

```bash
curl -s http://127.0.0.1:8190/api/health
# {"status":"ok","version":"0.1.0","comfy":"ok"}
TOKEN=<token-1>
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8190/api/catalog | head -c 300; echo
chmod +x ~/fashion-sketchpad/deploy/smoke.sh
~/fashion-sketchpad/deploy/smoke.sh http://127.0.0.1:8190 "$TOKEN"
```

`smoke.sh` cleans the sample sketch and renders it on `female_slim` as a camel tan cotton twill shirt,
which takes about 60 s on the GPU. It prints the exact prompt sent to ComfyUI and saves two files:

- `/tmp/fashion-smoke-check.png`: the placement check. Red is the sketch as placed, blue lines are
  neck/shoulders/waist/hips, and the green bar is the body's shoulder width. The collar should touch the
  neck line and the shoulders should span the green bar.
- `/tmp/fashion-smoke-render.png`: the render.

Copy them to Windows to look at them: `scp dct@10.4.18.27:/tmp/fashion-smoke-*.png .` Every job writes
the same check image, and you can fetch it for any render from `GET /api/jobs/<job_id>/<view>/check.png`.

## 5. Cloudflare tunnel

Edit `/etc/cloudflared/config.yml` and add this rule **above** the final `- service: http_status:404`:

```yaml
  - hostname: fashion-api.ucu-dct.org
    service: http://localhost:8190
```

Then validate, add the DNS record and restart. Run `route dns` as the user whose `~/.cloudflared/cert.pem`
created the tunnel; that's usually root, hence `sudo`.

```bash
sudo cloudflared tunnel --config /etc/cloudflared/config.yml ingress validate
sudo cloudflared tunnel --config /etc/cloudflared/config.yml ingress rule https://fashion-api.ucu-dct.org
sudo cloudflared tunnel route dns coolify fashion-api.ucu-dct.org
sudo systemctl restart cloudflared
```

From anywhere:

```bash
curl -s https://fashion-api.ucu-dct.org/api/health
./deploy/smoke.sh https://fashion-api.ucu-dct.org <token-1>
```

If requests from the app get a 403 with an HTML page, Cloudflare's bot protection is challenging the app.
Add a WAF skip rule for the hostname `fashion-api.ucu-dct.org` (Security > WAF > Custom rules > Skip).

## Updating

```powershell
git archive --format=tar.gz -o fashion-sketchpad.tar.gz HEAD
scp fashion-sketchpad.tar.gz dct@10.4.18.27:/home/dct/
```

```bash
tar -xzf ~/fashion-sketchpad.tar.gz -C ~/fashion-sketchpad
~/fashion-sketchpad/.venv/bin/pip install -r ~/fashion-sketchpad/gateway/requirements.txt
sudo systemctl restart fashion-gateway
```

Queued or running jobs survive the restart and continue when the service comes back.

## Housekeeping

- **Backups:** everything is in `/home/dct/fashion-data` (plain JSON and PNG). For example:
  `rsync -a /home/dct/fashion-data/ /backup/fashion-data/`.
- **ComfyUI folders:** each render leaves a control image in `ComfyUI/input/` (`fashion_*.png`) and the
  render in `ComfyUI/output/fashion/`. The gateway keeps its own copies, so these can be cleared. An
  optional weekly cron for `dct` (`crontab -e`):

  ```
  0 4 * * 0 find /home/dct/ComfyUI/input -name 'fashion_*.png' -mtime +7 -delete; find /home/dct/ComfyUI/output/fashion -name '*.png' -mtime +7 -delete
  ```
- **Cleaned uploads** that were never used for a design are deleted by the gateway after 3 days.
- **Adding body types:** run the template generator for the body. The new body shows up in the app the next
  time it loads the catalog. No restart needed.
- **Tuning wording:** edit `gateway/catalog.yaml`, then `sudo systemctl restart fashion-gateway`.

## Troubleshooting

| Symptom | Check |
|---|---|
| `"comfy":"unreachable"` in health | `systemctl status comfyui`; `curl -s 127.0.0.1:8188/system_stats` |
| Job view `error: ComfyUI rejected the workflow` | A model or node name changed. Check `journalctl -u fashion-gateway` for the node error and the model names in `RenderSettings` (`gateway/config.py`) |
| Body shows "not generated yet" | `ls /home/dct/ComfyUI/output/templates/<body>/`. It needs `front_guide.png` and `front_depth_*.png` |
| 401 from the app | The token in the app isn't in `APP_TOKENS`; restart the service after editing the env file |
| Renders slower than ~60 s per view | Something else is using GPU 1: `nvidia-smi` |
