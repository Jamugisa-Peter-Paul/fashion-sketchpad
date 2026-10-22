"use client";

import { ChevronDown } from "lucide-react";
import { Chip, Section, Segmented, cx } from "./ui";
import { CustomSwatch, Swatch } from "./Swatch";
import type { StyleChoice } from "@/lib/draft";
import type { Catalog } from "@/lib/types";

const SCENE_HINTS: Record<string, string> = {
  light_room: "Mannequin in a bright room with window light",
  plain_studio: "Mannequin on a plain grey backdrop",
  product_shot: "Garment only, ghost-mannequin style",
};

const FINISH_COLOURS: Record<string, string> = {
  matte_dark_grey: "#4a4a4c",
  chrome_silver: "linear-gradient(135deg, #f4f4f4, #9a9a9a 45%, #e6e6e6 60%, #7d7d7d)",
  matte_white: "#f1efec",
};

/** Colour (swatches, custom, prints) only; reused by the "Change colour" sheet. */
export function ColourPicker({ catalog, style, onChange }: { catalog: Catalog; style: StyleChoice; onChange: (c: Partial<StyleChoice>) => void }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-x-1 gap-y-3">
        {catalog.colours.map((colour) => (
          <Swatch
            key={colour.id}
            hex={colour.hex}
            label={colour.label}
            selected={!style.custom_hex && style.colour === colour.id}
            onClick={() => onChange({ colour: colour.id, custom_hex: null })}
          />
        ))}
        <CustomSwatch hex={style.custom_hex} selected={!!style.custom_hex} onPick={(hex) => onChange({ custom_hex: hex })} />
      </div>
      <div className="flex flex-wrap gap-2">
        {catalog.prints.map((print) => (
          <Chip key={print.id} selected={style.print === print.id} onClick={() => onChange({ print: print.id })}>
            {print.label}
          </Chip>
        ))}
      </div>
    </div>
  );
}

export function StylePicker({ catalog, style, onChange }: { catalog: Catalog; style: StyleChoice; onChange: (c: Partial<StyleChoice>) => void }) {
  const scene = catalog.scenes.find((s) => s.id === style.scene);
  return (
    <div className="grid gap-8 md:grid-cols-2 md:gap-10">
      <div className="space-y-8">
        <Section title="Colour">
          <ColourPicker catalog={catalog} style={style} onChange={onChange} />
        </Section>

        <Section title="Fabric">
          <div className="flex flex-wrap gap-2">
            {catalog.fabrics.map((fabric) => (
              <Chip key={fabric.id} selected={style.fabric === fabric.id} onClick={() => onChange({ fabric: fabric.id })}>
                {fabric.label}
              </Chip>
            ))}
          </div>
        </Section>

        <Section title="Fit">
          <Segmented options={catalog.fits} value={style.fit} onChange={(fit) => onChange({ fit })} />
        </Section>
      </div>

      <div className="space-y-8">
        <Section title="Details">
          <p className="text-sm font-medium">Buttons</p>
          <div className="flex flex-wrap gap-2">
            {catalog.buttons.map((b) => (
              <Chip key={b.id} selected={style.buttons === b.id} onClick={() => onChange({ buttons: b.id })}>
                {b.label}
              </Chip>
            ))}
          </div>
          <p className="pt-2 text-sm font-medium">Stitching</p>
          <Segmented options={catalog.stitching} value={style.stitching} onChange={(stitching) => onChange({ stitching })} />
        </Section>

        <Section title="Scene">
          <div className="grid gap-2">
            {catalog.scenes.map((s) => (
              <button
                key={s.id}
                type="button"
                aria-pressed={style.scene === s.id}
                onClick={() => onChange({ scene: s.id })}
                className={cx(
                  "flex min-h-14 items-center justify-between rounded-xl border-2 bg-surface px-4 py-2 text-left",
                  style.scene === s.id ? "border-ink" : "border-transparent",
                )}
              >
                <span>
                  <span className="block font-medium">{s.label}</span>
                  <span className="text-xs text-muted">{SCENE_HINTS[s.id] ?? ""}</span>
                </span>
                {s.default && <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-medium text-accent">Default</span>}
              </button>
            ))}
          </div>
        </Section>

        {scene?.on_mannequin !== false && (
          <Section title="Mannequin">
            <div className="flex gap-3">
              {catalog.mannequin_finishes.map((finish) => (
                <button
                  key={finish.id}
                  type="button"
                  aria-pressed={style.finish === finish.id}
                  onClick={() => onChange({ finish: finish.id })}
                  className="flex w-20 flex-col items-center gap-1"
                >
                  <span
                    className={cx(
                      "size-12 rounded-full border border-line",
                      style.finish === finish.id && "ring-2 ring-ink ring-offset-2 ring-offset-canvas",
                    )}
                    style={{ background: FINISH_COLOURS[finish.id] ?? "#888" }}
                  />
                  <span className="text-center text-[11px] leading-tight text-muted">{finish.label}</span>
                </button>
              ))}
            </div>
          </Section>
        )}

        <details className="group rounded-xl border border-line bg-surface" open={!!style.notes}>
          <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between px-4 text-sm font-medium">
            Extra notes (optional)
            <ChevronDown className="size-4 transition-transform group-open:rotate-180" />
          </summary>
          <div className="px-4 pb-4">
            <textarea
              value={style.notes}
              maxLength={300}
              rows={3}
              onChange={(e) => onChange({ notes: e.target.value })}
              placeholder="e.g. rolled sleeves, contrast collar"
              className="w-full rounded-lg border border-line p-3 text-base outline-none focus:border-ink"
            />
          </div>
        </details>
      </div>
    </div>
  );
}
