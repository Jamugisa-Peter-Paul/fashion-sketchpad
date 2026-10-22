"use client";

import { PersonStanding } from "lucide-react";
import { useAuthedImage } from "@/lib/useAuthedImage";
import type { ViewName } from "@/lib/types";

/** The body template's faint outline, drawn behind the sketch canvas. */
export function guidePath(body: string, view: ViewName): string {
  return `/api/templates/${body}/${view}/guide.png`;
}

/** Mannequin photo of a body template, cached for offline use. */
export function BodyThumb({ body, available }: { body: string; available: boolean }) {
  const { url } = useAuthedImage(available ? `/api/templates/${body}/front/photo.jpg` : null, { offline: true });
  if (!url) return <PersonStanding className="size-10 text-line" strokeWidth={1.5} />;
  // eslint-disable-next-line @next/next/no-img-element -- blob URL
  return <img src={url} alt="" className="h-full w-auto rounded-lg object-contain" />;
}
