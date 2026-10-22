"use client";

import { AlertCircle, Clock } from "lucide-react";
import { cx } from "./ui";
import { useAuthedImage } from "@/lib/useAuthedImage";
import { VIEW_LABELS, type ViewName, type ViewStatus } from "@/lib/types";

interface Props {
  view: ViewName;
  status: ViewStatus;
  imageUrl?: string | null;
  sketchUrl?: string | null;
  error?: string | null;
  /** 0..1 while running */
  progress?: number;
  onOpen?: (url: string) => void;
}

/** One view of a render: the image when done, otherwise the sketch with progress. */
export function RenderPanel({ view, status, imageUrl, sketchUrl, error, progress = 0, onOpen }: Props) {
  const { url } = useAuthedImage(status === "done" ? imageUrl : null);
  const { url: sketch } = useAuthedImage(status !== "done" ? sketchUrl : null);

  return (
    <figure className="flex min-w-0 flex-col gap-1.5">
      <div className="relative aspect-[832/1216] overflow-hidden rounded-2xl bg-surface shadow-[0_1px_8px_rgba(0,0,0,0.06)]">
        {url ? (
          <button type="button" className="size-full" onClick={() => onOpen?.(url)} aria-label={`Open ${VIEW_LABELS[view]} render`}>
            {/* eslint-disable-next-line @next/next/no-img-element -- blob URL */}
            <img src={url} alt={`${VIEW_LABELS[view]} render`} className="size-full object-cover" />
          </button>
        ) : (
          <>
            {sketch && (
              // eslint-disable-next-line @next/next/no-img-element -- blob URL
              <img src={sketch} alt="" className={cx("size-full object-contain p-4 opacity-30", status === "running" && "animate-pulse")} />
            )}
            <div className="absolute inset-x-3 bottom-3 space-y-2">
              {status === "error" ? (
                <p className="flex items-start gap-1.5 rounded-xl bg-red-50 p-2 text-xs text-danger">
                  <AlertCircle className="mt-0.5 size-4 shrink-0" />
                  {error ?? "Render failed"}
                </p>
              ) : (
                <>
                  <p className="flex items-center gap-1.5 text-xs font-medium text-muted">
                    {status === "queued" ? <Clock className="size-3.5" /> : null}
                    {status === "queued" ? "Waiting" : "Rendering"}
                  </p>
                  <div className="h-1.5 overflow-hidden rounded-full bg-line">
                    <div className="h-full rounded-full bg-accent transition-[width] duration-1000" style={{ width: `${Math.round(progress * 100)}%` }} />
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </div>
      <figcaption className="text-center text-xs font-medium text-muted">{VIEW_LABELS[view]}</figcaption>
    </figure>
  );
}
