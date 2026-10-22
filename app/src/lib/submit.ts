import { get } from "idb-keyval";
import { api, ApiError } from "./api";
import { photoKey, type DraftState } from "./draft";
import { exportDrawing, hasInk } from "./strokes";
import type { Catalog, GenerateRequest, StyleOptions, ViewName } from "./types";

const ALL_VIEWS: ViewName[] = ["front", "back", "side"];

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
      const drawn = draft.drawn[view];
      if (!hasInk(drawn)) continue;
      const png = await exportDrawing(drawn!);
      views[view] = { clean_id: (await cleanForm(png, `${view}.png`, "drawn", draft, view)).clean_id };
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
