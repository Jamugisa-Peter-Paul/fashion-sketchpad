import type { SketchDetails } from "./types";

// Construction details read off the sketch (gateway/details.py), shown as editable chips on the Style
// screen. `style.details === null` means "not read yet": the gateway then reads them itself at render time.

export type DetailGroup = "garment" | "front" | "back";

export const DETAIL_GROUPS: { id: DetailGroup; label: string }[] = [
  { id: "garment", label: "Whole garment" },
  { id: "front", label: "Front" },
  { id: "back", label: "Back" },
];

export const MAX_DETAILS = 8;
export const MAX_DETAIL_CHARS = 60;

export function emptyDetails(): SketchDetails {
  return { garment: [], front: [], back: [], side: [] };
}

export function cleanDetail(text: string): string {
  return text
    .replace(/[{}<>[\]"`]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[\s.,;:-]+|[\s.,;:-]+$/g, "")
    .toLowerCase()
    .slice(0, MAX_DETAIL_CHARS)
    .trim();
}

export function addDetail(details: SketchDetails, group: DetailGroup, text: string): SketchDetails {
  const item = cleanDetail(text);
  const list = details[group];
  if (!item || list.includes(item) || list.length >= MAX_DETAILS) return details;
  return { ...details, [group]: [...list, item] };
}

export function removeDetail(details: SketchDetails, group: DetailGroup, item: string): SketchDetails {
  return { ...details, [group]: details[group].filter((d) => d !== item) };
}

export function countDetails(details: SketchDetails | null | undefined): number {
  return details ? details.garment.length + details.front.length + details.back.length + details.side.length : 0;
}

/** FNV-1a: a cheap, stable fingerprint of a sketch, to tell when details (or a cleaned upload) are stale. */
export function fingerprint(text: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(36);
}
