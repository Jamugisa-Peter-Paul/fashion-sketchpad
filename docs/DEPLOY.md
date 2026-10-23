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

Optional render overrides (the defaults are shown): `RENDER_STEPS=28`, `RENDER_GUIDANCE=3.5`,
`VIEW_HINT=1`, and for the sketch-lines ControlNet (strength / end):

| | Product shot | On a mannequin (Light Room, Plain studio) |
|---|---|---|
| Paper sketch | `PAPER_LINES_STRENGTH=0.7` `PAPER_LINES_END=0.6` | `MANNEQUIN_PAPER_LINES_STRENGTH=0.8` `MANNEQUIN_PAPER_LINES_END=0.75` |
| Drawn in app | `DRAWN_LINES_STRENGTH=0.8` `DRAWN_LINES_END=0.7` | `MANNEQUIN_DRAWN_LINES_STRENGTH=0.85` `MANNEQUIN_DRAWN_LINES_END=0.8` |

Mannequin shape (depth ControlNet, on-mannequin scenes only): `DEPTH_STRENGTH=0.6` (0 turns it off),
`DEPTH_END=0.6`, and `DEPTH_GARMENT=fill`, which sets how the body depth is changed under the garment.
`fill` turns the drawn silhouette into a solid, so wide trousers and skirts are no longer pulled onto the
body; `blank` removes the depth under the garment (only the lines shape it); `off` is the old raw body
depth. Each job keeps the depth it used: `GET /api/jobs/<job_id>/<view>/depth.png`.
The old `LINES_STRENGTH` / `LINES_END` variables are no longer read.

To see exactly what a render was given, fetch
`GET /api/jobs/<job_id>/<view>/workflow.json` (ComfyUI API format, prompt included) or read
`prompt_<job_id>_<view>.txt` in the design folder.

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
# {"status":"ok","version":"0.1.0","comfy":"ok","details":"on"}   ("off" until section 6 is done)
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

## 6. Sketch details (vision LLM, optional)

Flux follows a sketch's shape but drops small things: buttons, ties, vents, pockets, embroidery. The gateway
can ask a vision model on llama-swap to list them. They go into the prompt and show up as editable chips
on the app's Style screen. Without it everything still works; renders just get no detail list.

**GPU memory first.** `qwen3.6-35b` is normally split over both GPUs, but GPU 1 is ComfyUI's (Flux takes
most of its 16 GB). Loading the 35B there while ComfyUI holds Flux will fail or push ComfyUI out of memory.
Add a second llama-swap entry that is the same model pinned to GPU 0, with some MoE experts on the CPU so it
fits. In llama-swap's config, copy your existing `qwen3.6-35b` entry (same model and `--mmproj` paths)
under a new name and change only what's marked:

```yaml
  qwen3.6-35b-vision:
    env:
      - "CUDA_VISIBLE_DEVICES=0"           # GPU 0 only, never ComfyUI's GPU
    cmd: >
      <same llama-server command and paths as qwen3.6-35b>
      --n-cpu-moe 16                       # experts on the CPU until it fits in 16 GB; lower = faster
      -c 8192                              # a sketch question needs little context
    ttl: 300                               # unload after 5 idle minutes
```

Restart llama-swap and check the entry loads on GPU 0 only (`nvidia-smi` while it answers). If it runs out
of memory, raise `--n-cpu-moe`. Then add to `/etc/fashion-gateway.env`:

```bash
LLM_URL=http://127.0.0.1:8085/v1
LLM_MODEL=qwen3.6-35b-vision
LLM_API_KEY=<the LLAMASWAP_API_KEY from /etc/llama-swap.env>
# LLM_TIMEOUT_S=240   # the first call loads the model; later ones take seconds
```

Run `sudo systemctl restart fashion-gateway`; health now shows `"details":"on"`. To try it, clean a sketch
and ask for its details:

```bash
CLEAN=$(curl -s -H "Authorization: Bearer $TOKEN" -F source=paper -F garment=jacket \
  -F image=@$HOME/fashion-sketchpad/gateway/tests/samples/garments/10_bomber_jacket_front.png \
  http://127.0.0.1:8190/api/sketch/clean | python3 -c 'import sys, json; print(json.load(sys.stdin)["clean_id"])')
curl -s -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"garment\": \"jacket\", \"views\": {\"front\": \"$CLEAN\"}}" http://127.0.0.1:8190/api/sketch/details
```

When the app sends no details (an older app, or the Style screen hadn't finished reading), the render
worker reads them itself before rendering, once per sketch. `GET /api/jobs/<id>` shows which details a
render used.

## 7. Regression renders

`gateway/tests/samples/garments/` holds 10 test garments (front and back). After changing wording or
strengths, render them all and compare contact sheets (about 2 minutes per garment per scene):

```bash
cd ~/fashion-sketchpad
APP_TOKEN=<token-1> .venv/bin/python -m gateway.tools.regression --url http://127.0.0.1:8190 \
  --scenes product_shot light_room --out ~/regression-$(date +%F)
# only some garments: --only 06 10      without the LLM: --no-details
```

Each garment gets its renders, placement checks and depth maps, plus `contact_<scene>.png` with one row per
garment (sketch front/back, render front/back).

## GPU power cap (recommended)

The first 5860 hard-reset under Flux load. Capping both A4000s from 140 W to 115 W costs a few seconds per
render and removes the power spikes. The limit resets on reboot, so set it from a small service:

```bash
sudo nvidia-smi -pm 1 && sudo nvidia-smi -pl 115     # right now
sudo tee /etc/systemd/system/gpu-power-cap.service >/dev/null <<'UNIT'
[Unit]
Description=Cap GPU power at 115 W

[Service]
Type=oneshot
ExecStart=/usr/bin/nvidia-smi -pm 1
ExecStart=/usr/bin/nvidia-smi -pl 115

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload && sudo systemctl enable gpu-power-cap
nvidia-smi --query-gpu=index,power.limit --format=csv   # 115.00 W on both
```

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
| `"details":"off"` in health | `LLM_URL` isn't set in `/etc/fashion-gateway.env` (section 6) |
| App says it couldn't read the details | `journalctl -u fashion-gateway \| grep -i details`. A 401 means `LLM_API_KEY` is wrong; a timeout means the model is still loading (try again) or doesn't fit on GPU 0 (raise `--n-cpu-moe`) |
| ComfyUI out of memory after reading details | The vision model landed on GPU 1: check its llama-swap entry has `CUDA_VISIBLE_DEVICES=0` and that `LLM_MODEL` names that entry |
| Garment on the mannequin comes out skinny, sheer or like a bodysuit | Look at `GET /api/jobs/<id>/<view>/depth.png`: the garment should be a solid grey shape. If it isn't, the outline wasn't closed; try `DEPTH_GARMENT=blank` |
