"use client";

import { X } from "lucide-react";
import { useEffect, type ReactNode } from "react";

/** Bottom sheet on phones, centred dialog on tablets. */
export function Sheet({ title, open, onClose, children, footer }: { title: string; open: boolean; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 md:items-center" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="safe-bottom max-h-[85dvh] w-full overflow-y-auto rounded-t-3xl bg-canvas md:max-w-lg md:rounded-3xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 flex items-center justify-between bg-canvas px-5 pb-2 pt-4">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button type="button" aria-label="Close" onClick={onClose} className="grid size-11 place-items-center rounded-full active:bg-line/60">
            <X className="size-5" />
          </button>
        </div>
        <div className="px-5 pb-4">{children}</div>
        {footer && <div className="sticky bottom-0 flex gap-3 bg-canvas px-5 pt-2">{footer}</div>}
      </div>
    </div>
  );
}
