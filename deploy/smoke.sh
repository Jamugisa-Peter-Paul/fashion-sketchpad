#!/usr/bin/env bash
# End-to-end smoke test: health -> catalog -> clean -> generate -> poll -> download.
#   ./deploy/smoke.sh http://127.0.0.1:8190 <token> [sketch.jpg]
#   ./deploy/smoke.sh https://fashion-api.ucu-dct.org <token>
# Needs curl and python3 (for JSON parsing; jq isn't always installed).
set -euo pipefail

BASE="${1:?usage: smoke.sh <base-url> <token> [image]}"
TOKEN="${2:?usage: smoke.sh <base-url> <token> [image]}"
IMAGE="${3:-$(dirname "$0")/../gateway/tests/samples/shirt_front_paper.jpeg}"
AUTH="Authorization: Bearer $TOKEN"
json() { python3 -c "import sys, json; print(json.load(sys.stdin)$1)"; }

echo "== health";  curl -fsS "$BASE/api/health"; echo
echo "== catalog: available bodies"
curl -fsS -H "$AUTH" "$BASE/api/catalog" | json "['bodies']" | python3 -c "
import ast, sys
for b in ast.literal_eval(sys.stdin.read()):
    if b['available']: print('  ', b['id'], b['views'])"

echo "== clean $IMAGE"
CLEAN_ID=$(curl -fsS -H "$AUTH" -F "image=@$IMAGE" -F source=paper -F garment=shirt -F body=female_slim "$BASE/api/sketch/clean" | json "['clean_id']")
echo "   clean_id=$CLEAN_ID"
curl -fsS -H "$AUTH" -o /tmp/fashion-smoke-lines.png "$BASE/api/sketch/$CLEAN_ID/lines.png" && echo "   lines -> /tmp/fashion-smoke-lines.png"

# A full, explicit style: camel tan cotton twill shirt with wooden buttons, Light Room, dark grey mannequin.
STYLE='{"garment":"shirt","body":"female_slim","colour":"camel","print":"plain","fabric":"cotton_twill","fit":"regular","buttons":"wood","stitching":"tonal","scene":"light_room","finish":"matte_dark_grey"}'

echo "== generate"
JOB=$(curl -fsS -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"title\":\"Smoke test\",\"style\":$STYLE,\"views\":{\"front\":{\"clean_id\":\"$CLEAN_ID\"}}}" \
  "$BASE/api/generate")
JOB_ID=$(echo "$JOB" | json "['job_id']")
DESIGN_ID=$(echo "$JOB" | json "['design_id']")
echo "   job_id=$JOB_ID design_id=$DESIGN_ID"

for _ in $(seq 1 120); do
  STATUS=$(curl -fsS -H "$AUTH" "$BASE/api/jobs/$JOB_ID")
  STATE=$(echo "$STATUS" | json "['status']")
  echo "   $STATE  eta=$(echo "$STATUS" | json "['eta_seconds'] or '-'")s"
  [[ "$STATE" == "done" || "$STATE" == "error" ]] && break
  sleep 5
done
echo "$STATUS"
echo "== prompt sent to ComfyUI"
curl -fsS -H "$AUTH" "$BASE/api/designs/$DESIGN_ID" | json "['renders'][-1]['views']['front']['prompt']"
curl -fsS -H "$AUTH" -o /tmp/fashion-smoke-check.png "$BASE/api/jobs/$JOB_ID/front/check.png" \
  && echo "== placement check saved to /tmp/fashion-smoke-check.png (red = sketch, blue = neck/shoulders/waist/hips)"
[[ "$STATE" == "done" ]] || { echo "FAILED"; exit 1; }
curl -fsS -H "$AUTH" -o /tmp/fashion-smoke-render.png "$BASE/api/jobs/$JOB_ID/front.png"
echo "== OK: render saved to /tmp/fashion-smoke-render.png"
