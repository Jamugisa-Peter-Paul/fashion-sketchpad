import { getStroke } from "perfect-freehand";
import type { DrawnView, Stroke } from "./draft";
import { CANVAS_H, CANVAS_W } from "./types";

// Strokes are stored as points in canvas pixels (832x1216, the render size) and turned into filled
// outlines with perfect-freehand. Pressure only changes the width for a stylus; fingers and mice draw
// at a constant width.

export const PEN_SIZES = [3, 6, 10] as const;
export const ERASER_SIZES = [12, 24, 48] as const;

export function strokeOutline(stroke: Stroke): number[][] {
  return getStroke(stroke.points, {
    size: stroke.size,
    thinning: stroke.pressure ? 0.65 : 0,
    smoothing: 0.5,
    streamline: 0.35,
    simulatePressure: false,
    last: true,
  });
}

/** SVG path for a perfect-freehand outline (quadratic curves through the midpoints). */
export function outlineToPath(points: number[][]): string {
  if (points.length === 0) return "";
  if (points.length < 3) {
    const [x, y] = points[0];
    return `M ${x} ${y} Z`;
  }
  const average = (a: number, b: number) => (a + b) / 2;
  let d = `M ${points[0][0].toFixed(2)} ${points[0][1].toFixed(2)} Q`;
  for (let i = 0; i < points.length; i++) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[(i + 1) % points.length];
    d += ` ${x0.toFixed(2)} ${y0.toFixed(2)} ${average(x0, x1).toFixed(2)} ${average(y0, y1).toFixed(2)}`;
  }
  return d + " Z";
}

/** Draws one stroke onto a context whose transform maps canvas pixels to the backing store. */
export function drawStroke(ctx: CanvasRenderingContext2D, stroke: Stroke): void {
  if (stroke.tool === "clear") {
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    ctx.restore();
    return;
  }
  const path = new Path2D(outlineToPath(strokeOutline(stroke)));
  ctx.globalCompositeOperation = stroke.tool === "eraser" ? "destination-out" : "source-over";
  ctx.fillStyle = "#111111";
  ctx.fill(path);
  ctx.globalCompositeOperation = "source-over";
}

/** Clears the context and replays the base image (if any) and every stroke. */
export function renderInk(ctx: CanvasRenderingContext2D, strokes: Stroke[], base?: CanvasImageSource | null): void {
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  ctx.restore();
  if (base) ctx.drawImage(base, 0, 0, CANVAS_W, CANVAS_H);
  for (const stroke of strokes) drawStroke(ctx, stroke);
}

/** True if the view still shows something after clears (erasers are ignored: good enough for "is it empty?"). */
export function hasInk(view: DrawnView | undefined): boolean {
  if (!view) return false;
  const lastClear = view.strokes.map((s) => s.tool).lastIndexOf("clear");
  const pensAfter = view.strokes.slice(lastClear + 1).some((s) => s.tool === "pen");
  return pensAfter || (!!view.base && lastClear === -1);
}

export function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Could not load image"));
    image.src = src;
  });
}

/** Black-on-white 832x1216 PNG of a drawn view, aligned to the body guide (what the gateway expects). */
export async function exportDrawing(view: DrawnView): Promise<Blob> {
  const ink = document.createElement("canvas");
  ink.width = CANVAS_W;
  ink.height = CANVAS_H;
  const inkCtx = ink.getContext("2d")!;
  renderInk(inkCtx, view.strokes, view.base ? await loadImage(view.base) : null);

  const out = document.createElement("canvas");
  out.width = CANVAS_W;
  out.height = CANVAS_H;
  const ctx = out.getContext("2d")!;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);
  ctx.drawImage(ink, 0, 0);
  return new Promise((resolve, reject) => out.toBlob((b) => (b ? resolve(b) : reject(new Error("Export failed"))), "image/png"));
}

/**
 * Turns a black-on-white sketch (from a saved design) into black-on-transparent, so it can be the base
 * layer of the canvas and be erased like ink.
 */
export async function sketchToBase(blob: Blob): Promise<string> {
  const bitmap = await createImageBitmap(blob);
  const canvas = document.createElement("canvas");
  canvas.width = CANVAS_W;
  canvas.height = CANVAS_H;
  const ctx = canvas.getContext("2d")!;
  ctx.drawImage(bitmap, 0, 0, CANVAS_W, CANVAS_H);
  const pixels = ctx.getImageData(0, 0, CANVAS_W, CANVAS_H);
  const data = pixels.data;
  for (let i = 0; i < data.length; i += 4) {
    const darkness = 255 - (data[i] + data[i + 1] + data[i + 2]) / 3;
    data[i] = data[i + 1] = data[i + 2] = 17;
    data[i + 3] = darkness < 12 ? 0 : darkness;
  }
  ctx.putImageData(pixels, 0, 0);
  return canvas.toDataURL("image/png");
}
