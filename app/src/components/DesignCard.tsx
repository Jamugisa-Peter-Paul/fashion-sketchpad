"use client";

import { ImageOff } from "lucide-react";
import Link from "next/link";
import { labelOf, useCatalog } from "@/lib/catalog";
import type { DesignSummary } from "@/lib/types";
import { useAuthedImage } from "@/lib/useAuthedImage";

export function DesignCard({ design }: { design: DesignSummary }) {
  const catalog = useCatalog((s) => s.catalog);
  const { url, failed } = useAuthedImage(design.thumbnail_url);
  const title = design.title || labelOf(catalog?.garments, design.garment);
  return (
    <Link href={`/design/?id=${design.id}`} className="group block overflow-hidden rounded-2xl border border-line bg-surface">
      <div className="aspect-[832/1216] bg-canvas">
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element -- blob URL, next/image can't optimise it
          <img src={url} alt={title} className="size-full object-cover" />
        ) : (
          <div className="grid size-full place-items-center text-muted">{failed && <ImageOff className="size-6" />}</div>
        )}
      </div>
      <div className="px-3 py-2">
        <p className="truncate text-sm font-medium">{title}</p>
        <p className="truncate text-xs text-muted">
          {labelOf(catalog?.bodies, design.body)} · {design.render_count} render{design.render_count === 1 ? "" : "s"}
        </p>
      </div>
    </Link>
  );
}
