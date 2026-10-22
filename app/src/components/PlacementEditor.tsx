"use client";

import { Minus, Plus, RotateCcw } from "lucide-react";
import { useRef, useState } from "react";
import { CANVAS_H, CANVAS_W, type Placement } from "@/lib/types";

interface Props {
  overlayUrl?: string;
  guideUrl?: string;
  /** Size of the cleaned sketch crop in px. */
  width: number;
  height: number;
  placement: Placement;
  /** Placement suggested by the server, for the reset button. */
  suggested?: Placement;
  /** Fixed placement (product shot): no dragging. */
  locked?: boolean;
  onChange: (placement: Placement) => void;
}

type Pointer = { x: number; y: number };

/**
 * Shows the cleaned sketch over the body outline. Drag to move, pinch (or +/-) to resize. The placement
 * is in canvas pixels (832x1216) and is sent to the gateway with the generate request.
 */
export function PlacementEditor({ overlayUrl, guideUrl, width, height, placement, suggested, locked, onChange }: Props) {
  const boxRef = useRef<HTMLDivElement>(null);
  const pointers = useRef(new Map<number, Pointer>());
  const gesture = useRef<{ start: Pointer[]; placement: Placement } | null>(null);
  // The in-progress value while dragging; ignored as soon as a new placement arrives from outside.
  const [drag, setDrag] = useState<{ from: Placement; value: Placement } | null>(null);
  const live = drag && drag.from === placement ? drag.value : null;
  const current = live ?? placement;
  const setLive = (value: Placement) => setDrag({ from: placement, value });

  /** CSS px per canvas px. */
  function ratio(): number {
    return (boxRef.current?.getBoundingClientRect().width ?? CANVAS_W) / CANVAS_W;
  }

  function startGesture() {
    gesture.current = { start: [...pointers.current.values()].map((p) => ({ ...p })), placement: current };
  }

  function onPointerDown(event: React.PointerEvent) {
    if (locked) return;
    boxRef.current!.setPointerCapture(event.pointerId);
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    startGesture();
  }

  function onPointerMove(event: React.PointerEvent) {
    const pointer = pointers.current.get(event.pointerId);
    const g = gesture.current;
    if (!pointer || !g) return;
    pointer.x = event.clientX;
    pointer.y = event.clientY;
    const now = [...pointers.current.values()];
    const k = ratio();
    if (g.start.length >= 2 && now.length >= 2) {
      const d0 = Math.hypot(g.start[1].x - g.start[0].x, g.start[1].y - g.start[0].y) || 1;
      const d1 = Math.hypot(now[1].x - now[0].x, now[1].y - now[0].y);
      const m0 = { x: (g.start[0].x + g.start[1].x) / 2, y: (g.start[0].y + g.start[1].y) / 2 };
      const m1 = { x: (now[0].x + now[1].x) / 2, y: (now[0].y + now[1].y) / 2 };
      setLive({
        cx: g.placement.cx + (m1.x - m0.x) / k,
        cy: g.placement.cy + (m1.y - m0.y) / k,
        scale: Math.min(Math.max(g.placement.scale * (d1 / d0), 0.05), 4),
      });
    } else if (g.start.length === 1) {
      setLive({
        ...g.placement,
        cx: g.placement.cx + (now[0].x - g.start[0].x) / k,
        cy: g.placement.cy + (now[0].y - g.start[0].y) / k,
      });
    }
  }

  function onPointerUp(event: React.PointerEvent) {
    pointers.current.delete(event.pointerId);
    if (pointers.current.size > 0) {
      startGesture(); // continue with the remaining finger without a jump
      return;
    }
    gesture.current = null;
    if (live) onChange(live);
  }

  function zoom(factor: number) {
    onChange({ ...current, scale: Math.min(Math.max(current.scale * factor, 0.05), 4) });
  }

  const w = width * current.scale;
  const h = height * current.scale;
  return (
    <div className="flex size-full flex-col items-center gap-2">
      <div className="relative min-h-0 w-full flex-1" style={{ containerType: "size" }}>
        <div className="absolute inset-0 flex items-center justify-center">
          <div
            ref={boxRef}
            className="no-touch-scroll relative aspect-[832/1216] overflow-hidden bg-white shadow-[0_1px_8px_rgba(0,0,0,0.08)]"
            style={{ width: "min(100cqw, calc(100cqh * 832 / 1216))" }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
          >
            {guideUrl && (
              // eslint-disable-next-line @next/next/no-img-element -- blob URL
              <img src={guideUrl} alt="" draggable={false} className="pointer-events-none absolute inset-0 size-full opacity-40" />
            )}
            {overlayUrl && (
              // eslint-disable-next-line @next/next/no-img-element -- blob URL
              <img
                src={overlayUrl}
                alt="Cleaned sketch"
                draggable={false}
                className="pointer-events-none absolute max-w-none"
                style={{
                  left: `${((current.cx - w / 2) / CANVAS_W) * 100}%`,
                  top: `${((current.cy - h / 2) / CANVAS_H) * 100}%`,
                  width: `${(w / CANVAS_W) * 100}%`,
                  height: `${(h / CANVAS_H) * 100}%`,
                }}
              />
            )}
          </div>
        </div>
      </div>
      {!locked && (
        <div className="flex items-center gap-1 rounded-2xl bg-surface p-1">
          <button type="button" aria-label="Smaller" onClick={() => zoom(1 / 1.08)} className="grid size-10 place-items-center rounded-xl active:bg-line/70">
            <Minus className="size-5" />
          </button>
          <button type="button" aria-label="Bigger" onClick={() => zoom(1.08)} className="grid size-10 place-items-center rounded-xl active:bg-line/70">
            <Plus className="size-5" />
          </button>
          {suggested && (
            <button type="button" onClick={() => onChange(suggested)} className="flex min-h-10 items-center gap-1.5 rounded-xl px-3 text-sm active:bg-line/70">
              <RotateCcw className="size-4" /> Auto
            </button>
          )}
          <span className="px-2 text-xs text-muted">Drag to move · pinch to resize</span>
        </div>
      )}
    </div>
  );
}
