"use client";

import { Check, Pipette } from "lucide-react";
import { cx } from "./ui";

function isLight(hex: string): boolean {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return 0.299 * r + 0.587 * g + 0.114 * b > 170;
}

export function Swatch({
  hex,
  label,
  selected,
  onClick,
}: {
  hex: string;
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick} aria-pressed={selected} aria-label={label} className="flex w-16 flex-col items-center gap-1">
      <span
        className={cx(
          "grid size-12 place-items-center rounded-full border transition-shadow",
          isLight(hex) ? "border-line" : "border-transparent",
          selected && "ring-2 ring-ink ring-offset-2 ring-offset-canvas",
        )}
        style={{ background: hex }}
      >
        {selected && <Check className={cx("size-5", isLight(hex) ? "text-ink" : "text-white")} />}
      </span>
      <span className="w-full truncate text-center text-[11px] text-muted">{label}</span>
    </button>
  );
}

/** A swatch that opens the system colour picker. */
export function CustomSwatch({ hex, selected, onPick }: { hex: string | null; selected: boolean; onPick: (hex: string) => void }) {
  return (
    <label className="flex w-16 cursor-pointer flex-col items-center gap-1">
      <span
        className={cx(
          "relative grid size-12 place-items-center rounded-full",
          selected && "ring-2 ring-ink ring-offset-2 ring-offset-canvas",
        )}
        style={{
          background: selected && hex ? hex : "conic-gradient(#e53935, #fdd835, #43a047, #1e88e5, #8e24aa, #e53935)",
        }}
      >
        <Pipette className={cx("size-5", selected && hex && isLight(hex) ? "text-ink" : "text-white")} />
        <input
          type="color"
          value={hex ?? "#c2a878"}
          onChange={(e) => onPick(e.target.value.toUpperCase())}
          className="absolute inset-0 size-full cursor-pointer opacity-0"
          aria-label="Custom colour"
        />
      </span>
      <span className="text-[11px] text-muted">{selected && hex ? hex : "Custom"}</span>
    </label>
  );
}
