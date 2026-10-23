import { get } from "idb-keyval";
import { api, ApiError } from "./api";
import { fingerprint } from "./details";
import { photoKey, useDraft, type DraftState, type DrawnView } from "./draft";
import { exportDrawing, hasInk } from "./strokes";
import type { Catalog, GenerateRequest, StyleOptions, ViewName } from "./types";

const ALL_VIEWS: ViewName[] = ["front", "back", "side"];
/** Cleaned uploads expire on the server after 3 days; reuse a drawn one for much less than that. */
const DRAWN_CLEAN_TTL_MS = 6 * 60 * 60 * 1000;

export function drawnSignature(view: DrawnView | undefined): string {
  return view ? fingerprint(JSON.stringify(view.strokes) + (view.base ?? "")) : "";
}

export function styleOptions(draft: DraftState): StyleOptions {
  return { ...draft.style, garment: draft.garment, body: draft.body };
}

function isOnMannequin(catalog: Catalog, sceneId: string): boolean {
  return catalog.scenes.find((s) => s.id === sceneId)?.on_mannequin !== false;
}

async function cleanForm(image: Blob, filename: string, source: "drawn" | "paper", draft: DraftState, view: ViewName) {
  const form = new FormData();
  form.append("image", image, filename);
  form.append("source", source);
  form.append("scene", draft.style.scene);
  form.append("garment", draft.garment);
  form.append("body", draft.body);
  form.append("view", view);
  form.append("whole_body", String(draft.paper[view]?.wholeBody ?? false));
  return api.clean(form);
}

/**
 * Uploads the sketches for a generate request. Drawn views are exported and cleaned now; paper views were
 * cleaned when added, so only their (possibly adjusted) placement is sent.
 */
export async function prepareViews(draft: DraftState, catalog: Catalog): Promise<GenerateRequest["views"]> {
  const views: GenerateRequest["views"] = {};
  if (draft.method === "draw") {
    for (const view of ALL_VIEWS) {
      if (!hasInk(draft.drawn[view])) continue;
      views[view] = { clean_id: await cleanDrawnView(draft, view) };
    }
    return views;
  }
  const onMannequin = isOnMannequin(catalog, draft.style.scene);
  for (const view of ALL_VIEWS) {
    const paper = draft.paper[view];
    if (!paper?.cleanId) continue;
    // A placement made for the other kind of scene doesn't apply; the gateway then works one out.
    const placement = onMannequin && paper.cleanedFor === "mannequin" ? paper.placement : undefined;
    views[view] = { clean_id: paper.cleanId, ...(placement ? { placement } : {}) };
  }
  return views;
}

/** Uploads + cleans a drawn view, or reuses the upload made for the same strokes a little earlier. */
export async function cleanDrawnView(draft: DraftState, view: ViewName): Promise<string> {
  const drawn = draft.drawn[view]!;
  const sig = drawnSignature(drawn);
  const cached = draft.drawnClean?.[view];
  if (cached && cached.sig === sig && Date.now() - cached.at < DRAWN_CLEAN_TTL_MS) return cached.cleanId;
  const png = await exportDrawing(drawn);
  const cleanId = (await cleanForm(png, `${view}.png`, "drawn", draft, view)).clean_id;
  useDraft.setState((s) => ({ drawnClean: { ...s.drawnClean, [view]: { cleanId, sig, at: Date.now() } } }));
  return cleanId;
}

/**
 * Which sketches the details belong to: garment + each view's cleaned upload (or drawing). When this
 * changes, the details on screen are for another sketch and are read again. "" = nothing to read.
 */
export function detailsKey(draft: DraftState): string {
  const parts: string[] = [];
  for (const view of ALL_VIEWS) {
    if (draft.method === "draw") {
      if (hasInk(draft.drawn[view])) parts.push(`${view}:${drawnSignature(draft.drawn[view])}`);
    } else if (draft.paper[view]?.cleanId) {
      parts.push(`${view}:${draft.paper[view]!.cleanId}`);
    }
  }
  return parts.length ? `${draft.garment}|${parts.join(",")}` : "";
}

/** Clean ids of the sketches to read details from (drawn views are uploaded now, and reused later). */
export async function detailsViews(draft: DraftState): Promise<Partial<Record<ViewName, string>>> {
  const views: Partial<Record<ViewName, string>> = {};
  for (const view of ALL_VIEWS) {
    if (draft.method === "draw") {
      if (hasInk(draft.drawn[view])) views[view] = await cleanDrawnView(draft, view);
    } else if (draft.paper[view]?.cleanId) {
      views[view] = draft.paper[view]!.cleanId;
    }
  }
  return views;
}

/**
 * Cleaned uploads expire on the server after a few days. Re-clean the stored photos; the crop comes out
 * the same, so the user's placement still applies. Returns the new clean ids.
 */
export async function recleanPaper(draft: DraftState): Promise<Partial<Record<ViewName, string>>> {
  const ids: Partial<Record<ViewName, string>> = {};
  for (const view of ALL_VIEWS) {
    if (!draft.paper[view]?.cleanId) continue;
    const photo = (await get(photoKey(view))) as Blob | undefined;
    if (!photo) throw new ApiError(422, `The ${view} photo is no longer on this device. Please add it again.`);
    ids[view] = (await cleanForm(photo, "sketch.jpg", "paper", draft, view)).clean_id;
  }
  return ids;
}

export function isExpiredError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 422 && /expired/i.test(error.message);
}
