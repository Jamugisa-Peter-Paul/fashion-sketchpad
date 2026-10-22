import { fetchBlob } from "./api";
import { useDraft, type DrawnView, type StyleChoice } from "./draft";
import { sketchToBase } from "./strokes";
import type { Catalog, DesignOut, ViewName } from "./types";

/**
 * Loads a saved design into the draft so it can be tweaked. Drawn sketches come back as an editable base
 * layer; paper designs keep using the sketches stored on the server until a new photo is added.
 */
export async function openDesign(design: DesignOut, catalog: Catalog | null): Promise<"draw" | "upload"> {
  const views = Object.entries(design.views) as [ViewName, NonNullable<DesignOut["views"][ViewName]>][];
  const method = views.some(([, v]) => v.source === "paper") ? "upload" : "draw";
  const drawn: Partial<Record<ViewName, DrawnView>> = {};
  if (method === "draw") {
    for (const [view] of views) {
      const url = design.sketch_urls[view];
      if (url) drawn[view] = { strokes: [], base: await sketchToBase(await fetchBlob(url)) };
    }
  }
  const { garment, body, ...style } = design.style;
  const group = catalog?.bodies.find((b) => b.id === body)?.group ?? "women";
  useDraft.getState().reset({
    method,
    group,
    body,
    garment,
    drawn,
    paper: {},
    style: style as StyleChoice,
    designId: design.id,
    jobId: design.renders.at(-1)?.id,
    lastSeed: design.renders.at(-1)?.seed,
    title: design.title,
  });
  return method;
}
