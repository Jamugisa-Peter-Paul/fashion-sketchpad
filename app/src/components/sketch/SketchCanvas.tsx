"use client";

import { Maximize2 } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Stroke, Tool } from "@/lib/draft";
import { drawStroke, loadImage, renderInk } from "@/lib/strokes";
import { CANVAS_H, CANVAS_W } from "@/lib/types";

/** Backing-store pixels per canvas pixel, so lines stay crisp when zoomed on high-DPI screens. */
const RES = 2;
const MAX_ZOOM = 5;

interface Props {
  strokes: Stroke[];
  /** Earlier drawing (black on transparent) to draw on top of. */
  base?: string;
  guideUrl?: string;
  showGuide: boolean;
  tool: Tool;
  size: number;
  /** Called with the full new stroke list when a stroke is finished. */
  onChange: (strokes: Stroke[]) => void;
}

interface ViewTransform {
  zoom: number;
  x: number;
  y: number;
}

type Point = { x: number; y: number; type: string };

/**
 * Drawing surface over the faint body guide. One finger, mouse or stylus draws; two fingers pinch and pan.
 * Once a stylus has been used, single-finger touches pan instead of drawing (palm rejection).
 */
export function SketchCanvas({ strokes, base, guideUrl, showGuide, tool, size, onChange }: Props) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const committedRef = useRef<HTMLCanvasElement | null>(null);
  const baseImageRef = useRef<HTMLImageElement | null>(null);
  const strokesRef = useRef(strokes);
  const renderedRef = useRef<Stroke[] | null>(null);
  const currentRef = useRef<{ id: number; stroke: Stroke } | null>(null);
  const pointersRef = useRef(new Map<number, Point>());
  const gestureRef = useRef<{ start: Point[]; view: ViewTransform } | null>(null);
  const penSeenRef = useRef(false);
  const frameRef = useRef(0);
  const [layout, setLayout] = useState({ vw: 0, vh: 0, w: 0, h: 0 });
  const [view, setView] = useState<ViewTransform>({ zoom: 1, x: 0, y: 0 });
  const viewRef = useRef(view);
  // Event handlers read the latest values through refs; layout effects run before the redraw effects.
  useLayoutEffect(() => {
    viewRef.current = view;
  }, [view]);
  useLayoutEffect(() => {
    strokesRef.current = strokes;
  }, [strokes]);

  const paint = useCallback(() => {
    const canvas = canvasRef.current;
    const committed = committedRef.current;
    if (!canvas || !committed) return;
    const ctx = canvas.getContext("2d")!;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(committed, 0, 0);
    if (currentRef.current) {
      ctx.setTransform(RES, 0, 0, RES, 0, 0);
      drawStroke(ctx, currentRef.current.stroke);
    }
  }, []);

  const redrawAll = useCallback(() => {
    const committed = committedRef.current;
    if (!committed) return;
    const ctx = committed.getContext("2d")!;
    ctx.setTransform(RES, 0, 0, RES, 0, 0);
    renderInk(ctx, strokesRef.current, baseImageRef.current);
    renderedRef.current = strokesRef.current;
    paint();
  }, [paint]);

  // Canvases are created once at the fixed render size.
  useEffect(() => {
    const canvas = canvasRef.current!;
    canvas.width = CANVAS_W * RES;
    canvas.height = CANVAS_H * RES;
    const committed = document.createElement("canvas");
    committed.width = CANVAS_W * RES;
    committed.height = CANVAS_H * RES;
    committedRef.current = committed;
    redrawAll();
  }, [redrawAll]);

  useEffect(() => {
    let cancelled = false;
    if (!base) {
      baseImageRef.current = null;
      redrawAll();
      return;
    }
    loadImage(base).then((image) => {
      if (cancelled) return;
      baseImageRef.current = image;
      redrawAll();
    });
    return () => {
      cancelled = true;
    };
  }, [base, redrawAll]);

  // Undo/redo/clear/view switches arrive as a new stroke list; strokes we just drew are already painted.
  useEffect(() => {
    if (strokes !== renderedRef.current) redrawAll();
  }, [strokes, redrawAll]);

  // Fit the 832x1216 page inside the available space.
  useEffect(() => {
    const viewport = viewportRef.current!;
    const observer = new ResizeObserver(([entry]) => {
      const { width: vw, height: vh } = entry.contentRect;
      const ratio = CANVAS_W / CANVAS_H;
      const w = vw / vh > ratio ? vh * ratio : vw;
      setLayout({ vw, vh, w, h: w / ratio });
      setView({ zoom: 1, x: 0, y: 0 });
    });
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);

  const clampView = useCallback(
    (next: ViewTransform): ViewTransform => {
      const zoom = Math.min(Math.max(next.zoom, 1), MAX_ZOOM);
      const minX = layout.w * (1 - zoom);
      const minY = layout.h * (1 - zoom);
      return { zoom, x: Math.min(0, Math.max(minX, next.x)), y: Math.min(0, Math.max(minY, next.y)) };
    },
    [layout.w, layout.h],
  );

  function toCanvas(event: { clientX: number; clientY: number; pressure: number; pointerType: string }): [number, number, number] {
    const rect = stageRef.current!.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * CANVAS_W;
    const y = ((event.clientY - rect.top) / rect.height) * CANVAS_H;
    const pressure = event.pointerType === "pen" ? event.pressure || 0.5 : 0.5;
    return [Math.round(x * 10) / 10, Math.round(y * 10) / 10, Math.round(pressure * 100) / 100];
  }

  function scheduleFrame() {
    if (frameRef.current) return;
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = 0;
      paint();
    });
  }

  /** Position relative to the stage's untransformed top-left corner. */
  function local(point: Point): { x: number; y: number } {
    const viewport = viewportRef.current!.getBoundingClientRect();
    return { x: point.x - viewport.left - (layout.vw - layout.w) / 2, y: point.y - viewport.top - (layout.vh - layout.h) / 2 };
  }

  function startGesture(points: Point[]) {
    gestureRef.current = { start: points.map((p) => ({ ...p })), view: viewRef.current };
  }

  function updateGesture() {
    const gesture = gestureRef.current;
    if (!gesture) return;
    const touches = [...pointersRef.current.values()].filter((p) => p.type === "touch");
    const { view: start } = gesture;
    if (gesture.start.length >= 2 && touches.length >= 2) {
      const [a0, b0] = gesture.start.map(local);
      const [a1, b1] = touches.slice(0, 2).map(local);
      const d0 = Math.hypot(b0.x - a0.x, b0.y - a0.y) || 1;
      const d1 = Math.hypot(b1.x - a1.x, b1.y - a1.y);
      const zoom = Math.min(Math.max((start.zoom * d1) / d0, 1), MAX_ZOOM);
      const m0 = { x: (a0.x + b0.x) / 2, y: (a0.y + b0.y) / 2 };
      const m1 = { x: (a1.x + b1.x) / 2, y: (a1.y + b1.y) / 2 };
      // Keep the content point that was under the fingers' midpoint under it.
      const cx = (m0.x - start.x) / start.zoom;
      const cy = (m0.y - start.y) / start.zoom;
      setView(clampView({ zoom, x: m1.x - zoom * cx, y: m1.y - zoom * cy }));
    } else if (gesture.start.length === 1 && touches.length === 1) {
      const p0 = local(gesture.start[0]);
      const p1 = local(touches[0]);
      setView(clampView({ zoom: start.zoom, x: start.x + p1.x - p0.x, y: start.y + p1.y - p0.y }));
    }
  }

  function onPointerDown(event: React.PointerEvent) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    if (event.pointerType === "pen") penSeenRef.current = true;
    pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY, type: event.pointerType });
    viewportRef.current!.setPointerCapture(event.pointerId);

    const touches = [...pointersRef.current.values()].filter((p) => p.type === "touch");
    if (event.pointerType === "touch") {
      if (touches.length >= 2) {
        // A second finger turns a stroke that just started into a pinch.
        if (currentRef.current && pointersRef.current.get(currentRef.current.id)?.type === "touch") {
          currentRef.current = null;
          paint();
        }
        startGesture(touches.slice(0, 2));
        return;
      }
      if (penSeenRef.current) {
        startGesture(touches);
        return;
      }
    }
    if (gestureRef.current || currentRef.current) return;

    currentRef.current = {
      id: event.pointerId,
      stroke: { tool, size, pressure: event.pointerType === "pen", points: [toCanvas(event)] },
    };
    scheduleFrame();
  }

  function onPointerMove(event: React.PointerEvent) {
    const pointer = pointersRef.current.get(event.pointerId);
    if (!pointer) return;
    pointer.x = event.clientX;
    pointer.y = event.clientY;
    if (gestureRef.current) {
      updateGesture();
      return;
    }
    const current = currentRef.current;
    if (current?.id !== event.pointerId) return;
    const native = event.nativeEvent;
    const events = typeof native.getCoalescedEvents === "function" ? native.getCoalescedEvents() : [];
    for (const e of events.length ? events : [native]) current.stroke.points.push(toCanvas(e));
    scheduleFrame();
  }

  function onPointerEnd(event: React.PointerEvent) {
    pointersRef.current.delete(event.pointerId);
    const current = currentRef.current;
    if (current?.id === event.pointerId) {
      currentRef.current = null;
      if (event.type === "pointercancel") {
        paint();
      } else {
        const committed = committedRef.current!.getContext("2d")!;
        committed.setTransform(RES, 0, 0, RES, 0, 0);
        drawStroke(committed, current.stroke);
        const next = [...strokesRef.current, current.stroke];
        renderedRef.current = next;
        paint();
        onChange(next);
      }
    }
    if (gestureRef.current) {
      const touches = [...pointersRef.current.values()].filter((p) => p.type === "touch");
      // Lifting one finger of a pinch ends it; the remaining finger must not start drawing.
      if (touches.length === 0) gestureRef.current = null;
      else startGesture(touches.slice(0, 2));
    }
  }

  function onWheel(event: React.WheelEvent) {
    const rect = stageRef.current!.getBoundingClientRect();
    const zoom = Math.min(Math.max(view.zoom * (event.deltaY < 0 ? 1.15 : 1 / 1.15), 1), MAX_ZOOM);
    const p = local({ x: event.clientX, y: event.clientY, type: "mouse" });
    const cx = (event.clientX - rect.left) / view.zoom;
    const cy = (event.clientY - rect.top) / view.zoom;
    setView(clampView({ zoom, x: p.x - zoom * cx, y: p.y - zoom * cy }));
  }

  return (
    <div
      ref={viewportRef}
      className="no-touch-scroll relative size-full overflow-hidden"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      onWheel={onWheel}
      onContextMenu={(e) => e.preventDefault()}
    >
      <div
        ref={stageRef}
        className="absolute bg-white shadow-[0_1px_8px_rgba(0,0,0,0.08)]"
        style={{
          width: layout.w,
          height: layout.h,
          left: (layout.vw - layout.w) / 2,
          top: (layout.vh - layout.h) / 2,
          transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})`,
          transformOrigin: "0 0",
          cursor: tool === "pen" ? "crosshair" : "cell",
        }}
      >
        {guideUrl && showGuide && (
          // eslint-disable-next-line @next/next/no-img-element -- blob URL
          <img src={guideUrl} alt="" draggable={false} className="pointer-events-none absolute inset-0 size-full opacity-40" />
        )}
        <canvas ref={canvasRef} className="absolute inset-0 size-full" />
      </div>

      {view.zoom > 1.01 && (
        <button
          type="button"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => setView({ zoom: 1, x: 0, y: 0 })}
          className="absolute right-3 top-3 flex min-h-10 items-center gap-1 rounded-full bg-ink/80 px-3 text-xs font-medium text-white"
        >
          <Maximize2 className="size-4" /> {Math.round(view.zoom * 100)}%
        </button>
      )}
    </div>
  );
}
