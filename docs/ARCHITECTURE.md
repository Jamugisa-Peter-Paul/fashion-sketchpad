# Architecture

Fashion Sketchpad turns garment sketches into photoreal renders using the ComfyUI server that already
runs on the Precision 5860. Users never type prompts. They draw or upload a sketch and tap choices, and the
gateway turns those choices into a ComfyUI workflow.

```
 Android app (Capacitor + Next.js static export)
        │  HTTPS, Authorization: Bearer <token>
        ▼
 Cloudflare Tunnel  fashion-api.ucu-dct.org ──► localhost:8190
        ▼
 gateway (FastAPI, systemd fashion-gateway, user dct)
   ├─ catalog.yaml          choices + the prompt words for each
   ├─ sketch cleaning       paper photo / drawn PNG ─► white-lines-on-black control image
   ├─ prompt builder        options ─► prompt per view (pure, unit-tested)
   ├─ workflow builder      prompt + images ─► ComfyUI API JSON
   ├─ job queue             one worker, jobs run serially (one GPU)
   └─ DATA_DIR              designs, sketches, renders, job state as JSON
        │  http://127.0.0.1:8188 (never exposed)
        ▼
 ComfyUI (systemd comfyui, GPU 1): Flux Dev Q6_K + ControlNet Union Pro 2.0
```

## Repo layout

| Path | What |
|---|---|
| `gateway/` | Python package (run from the repo root: `uvicorn gateway.main:create_app --factory`) |
| `gateway/catalog.yaml` | Garments, fabrics, colours, prints, fits, details, scenes, finishes, bodies |
| `gateway/tests/` | pytest suite. A fake ComfyUI means no GPU is needed |
| `gateway/tools/` | CLIs, e.g. `python -m gateway.tools.clean <img>` |
| `app/` | Next.js + Tailwind (static export) wrapped by Capacitor for Android |
| `docs/` | This file, deployment and app build notes |

## Gateway

**Config** comes from environment variables (see `gateway/.env.example`): `COMFY_URL`, `TEMPLATES_DIR`,
`DATA_DIR`, `APP_TOKENS`, `PUBLIC_BASE_URL`, `CORS_ORIGINS`, `MAX_UPLOAD_MB`.

**Auth.** Every endpoint except `GET /api/health` needs `Authorization: Bearer <token>`, where the token is
one of `APP_TOKENS`. Images are protected too, so the app fetches them with the header and displays them
as blob URLs. Tokens never go into URLs.

**Endpoints**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness (public) |
| GET | `/api/catalog` | All choices, plus each body's available template views |
| GET | `/api/templates/{body}/{view}/guide.png` | Faint body outline to draw over |
| POST | `/api/sketch/clean` | Image + source (`paper`/`drawn`) + scene/garment/body/view ─► `{clean_id, width, height, placement, lines_url, overlay_url}` |
| GET | `/api/sketch/{clean_id}/lines.png`, `/overlay.png` | Cleaned crop: white-on-black (model input) / dark-on-transparent (for the editor) |
| POST | `/api/generate` | JSON `{design_id?, title?, style, views: {front: {clean_id, placement?}}, seed?}` ─► 202 `{job_id, design_id}` |
| GET | `/api/jobs/{id}` | `{status, seed, position, eta_seconds, views: {front: {status, error, image_url}}}` |
| GET | `/api/jobs/{id}/{view}.png` | Render |
| GET | `/api/designs` | Gallery summaries with thumbnail URL |
| GET/PATCH/DELETE | `/api/designs/{id}` | Full design with render history / rename / delete |
| GET | `/api/designs/{id}/{sketch\|lines}/{view}.png` | Stored sketch and cleaned lines, for "Edit sketch" |

`style` is `StyleOptions` in `gateway/prompts.py`: catalog ids for garment, body, colour (or
`custom_hex`), print, fabric, fit, buttons, stitching, scene, finish, plus `notes`. *New variation*
posts the same style with no seed. *Change colour* posts a new style with the seed of the render it
changes. For an existing design, `views` may be empty, which reuses the stored sketches.

**Templates** are found on disk, not configured:
`TEMPLATES_DIR/<body>/<view>_{guide,mask}.png` and `<view>_{photo,depth}_*.png`. A view is *available*
when its guide and depth files exist. A body is *available* when its front view is. Missing bodies still
appear in the catalog with `available: false`, so the app can show them as "not generated yet".

### Render pipeline

1. **Clean** each view's sketch into white lines on black at 832×1216.
   - *Paper* (`gateway/sketch.py`), at a fixed 1216 px working size: grayscale, mask out the table
     or pencil if the photo shows them, divide by a heavy Gaussian blur (σ≈25) to flatten the paper
     lighting, darkness boost ≈1.5 minus 25, remove specks under 25 px. Then keep only the garment: the
     heaviest cluster of strokes, grown by clusters inside its convex hull (pockets, seams) or nearby,
     tall and not cut off by the photo or paper edge. Labels, notes and neighbouring sketches fail
     those tests and are dropped, so they don't get printed into the render.
   - *Drawn:* flatten onto white and invert. Kept aligned with the template.
   - *Placement:* for on-mannequin scenes a cropped paper sketch is auto-placed on the body by garment
     `placement` (`gateway/placement.py`). The body is measured from the template mask at fixed
     fractions of its height: neck 16%, shoulders 20% (shoulder width measured there), waist 38%,
     hips 50%. For tops and full-length garments the sketch's own shoulder width (where the shoulder
     seams turn into sleeves) is scaled to the body's, with the collar at the neck. The sketch's
     proportions then carry the hem to the hips, knees or floor. Bottoms match the waistband to the
     waist, and `figure` (whole-body sketches) maps head to feet. The app shows it over the guide and the
     user can drag or pinch to adjust before generating.
   - *Product shot:* crop to the bounding box plus 30 px and scale to fill about 94% of the canvas.
   Every sketch, drawn or photographed, goes through `/api/sketch/clean` once. Generate then refers to
   its `clean_id` plus the final placement, so images are uploaded only once.
2. **Prompt.** Scene template + garment description built from the catalog. Front and back use the same
   seed and identical colour and fabric wording. Explicit colour names with hex reduce drift.
3. **Workflow** (`gateway/workflow.py`). Pure text-to-image: KSampler (euler/simple, 28 steps, cfg 1,
   denoise 1.0) starts from an EmptySD3LatentImage at 832×1216. Nothing from the sketch is encoded into
   the latent or blended into the result. The sketch (white lines on black) is only a ControlNet Union
   Pro 2.0 hint: strength 0.7 / end 0.6 for paper sketches, 0.8 / 0.7 for drawn ones (stronger or longer
   and Flux copies the lines as black outlines with a flat fill). Enlarged sketches use linear
   interpolation, and grey below 40 is dropped, so no soft fringe reaches the ControlNet. In on-mannequin
   scenes a second ControlNet uses the mannequin template's depth at strength 0.6 / end 0.7 for the
   mannequin's shape and pose; it's off for product shots. On-mannequin prompts start with "a faceless
   matte dark grey fashion mannequin wearing the garment" (the finish follows the user's choice).
   FluxGuidance 3.5. A test (`gateway/tests/workflow_checks.py`) asserts the images only feed
   ControlNet inputs.
4. **Queue** (`gateway/jobs.py`). One worker submits views one after another (`/upload/image`,
   `/prompt`, poll `/history/{id}`, `/view`) and copies results into the design folder. Expect about
   60 s per view. The ComfyUI `prompt_id` is saved, so after a gateway restart a view ComfyUI still
   knows about is collected, not rendered again.

Render settings (steps, guidance, ControlNet strengths, the "Back view." hint) default to the proven
recipe and can be overridden with env vars. See `RenderSettings` in `gateway/config.py`.

### Data on disk

```
DATA_DIR/uploads/<clean_id>/   sketch.png, lines.png, meta.json (deleted after 3 days)
DATA_DIR/designs/<design_id>/
  design.json            choices, input method, body, garment, render history
  sketch_<view>.png      what the user drew / uploaded (normalised)
  lines_<view>.png       cleaned lines crop (full canvas for drawn sketches)
  control_<view>.png     last 832x1216 control image sent to ComfyUI
  check_<job_id>_<view>.png  placement check: control lines over the template with neck/shoulder/waist/hip
                         lines (GET /api/jobs/{id}/{view}/check.png)
  workflow_<job_id>_<view>.json  exact ComfyUI workflow queued (GET /api/jobs/{id}/{view}/workflow.json)
  prompt_<job_id>_<view>.txt     final prompt text
  render_<job_id>_<view>.png
```

Each generate call is a *job* recorded in its design's render history (seed, options, status per view).
Every render is kept. "New variation" adds a job with a new seed. "Change colour" adds a job with the same
seed and different colour options. On restart, unfinished jobs are re-queued.

## App

- Next.js App Router with `output: "export"`. Routes use query parameters (`/design?id=…`) because static
  export can't pre-render unknown ids.
- Tailwind, mobile-first. Tablets get side-by-side panels.
- Wizard state is held in a small store. Drafts, including stroke vectors so undo survives a crash, are
  saved to IndexedDB.
- Drawing uses Pointer Events with pressure (stylus) and a constant width when pressure isn't reported
  (most fingers). The export is black on white, 832×1216, aligned to the guide.
- The token is kept in Capacitor Preferences. The gateway URL comes from `NEXT_PUBLIC_API_URL`, and can
  be changed on the login screen.
- Capacitor plugins: Preferences, Filesystem (Save), Share. Photos are taken with a plain
  `<input type="file" capture>`, which the Capacitor webview hands to the camera app, so no Camera plugin
  or camera permission is needed.
- Every sketch goes through `/api/sketch/clean`. Drawn sketches are exported and cleaned when you tap
  Generate. Paper photos are cleaned when added, so the user can check the preview and adjust the
  placement. A reopened design re-renders from the sketches stored on the server.
- See [APP.md](APP.md) for screens, local development and the APK build.

## Decisions and known limits

- ComfyUI is never exposed. Only the gateway is reachable, through the Cloudflare tunnel, and it listens
  on 127.0.0.1.
- Progress is estimated from queue position and elapsed time against about 60 s per view. Per-step
  progress over ComfyUI's websocket can be added later.
- "Change colour" re-renders with the same seed, so construction stays close but not identical.
- Catalog prompt wording is a first draft. Regional garments (gomesi, kanzu) and fabrics (kitenge,
  barkcloth) are described in plain words because Flux doesn't know the names well. Tune them in
  `catalog.yaml`.
