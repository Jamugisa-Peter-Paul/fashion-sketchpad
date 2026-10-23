"use client";

import { del, get, set } from "idb-keyval";
import { useSyncExternalStore } from "react";
import { create } from "zustand";
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";
import type { Catalog, Group, Placement, StyleOptions, ViewName } from "./types";
import { defaultId } from "./catalog";
import { hasInk } from "./strokes";

// The design being worked on. Persisted to IndexedDB after every change, so closing the app (or a crash)
// never loses a sketch. Photo blobs live under their own keys (see photoKey) because they aren't JSON.

export type Method = "draw" | "upload";
export type Tool = "pen" | "eraser";

/** A stroke in canvas pixels (832x1216). `clear` wipes everything drawn before it (undoable). */
export interface Stroke {
  tool: Tool | "clear";
  size: number;
  /** [x, y, pressure] */
  points: [number, number, number][];
  /** Whether pressure came from a stylus (otherwise constant width). */
  pressure: boolean;
}

export interface DrawnView {
  strokes: Stroke[];
  /** Data URL of an earlier drawing (black on transparent) to keep drawing on, when reopening a design. */
  base?: string;
}

export interface PaperView {
  /** Set once the photo is cleaned by the gateway. */
  cleanId?: string;
  width?: number;
  height?: number;
  placement?: Placement;
  /** Placement the gateway suggested, for the "Auto" reset button. */
  suggested?: Placement;
  /** Whether the sketch shows a whole figure (affects auto-placement). */
  wholeBody: boolean;
  /** Scene kind the placement was made for: placements differ between on-mannequin and product shot. */
  cleanedFor?: "mannequin" | "product";
}

export type StyleChoice = Omit<StyleOptions, "garment" | "body">;

/** A drawn view already uploaded and cleaned (for reading details), reused at generate time if unchanged. */
export interface DrawnClean {
  cleanId: string;
  /** fingerprint of the strokes it was made from */
  sig: string;
  at: number;
}

export interface DraftState {
  method: Method;
  group: Group;
  body: string;
  garment: string;
  drawn: Partial<Record<ViewName, DrawnView>>;
  paper: Partial<Record<ViewName, PaperView>>;
  style: StyleChoice;
  /** Which sketches `style.details` were read from (see detailsKey); other sketches = read again. */
  detailsFor?: string;
  drawnClean: Partial<Record<ViewName, DrawnClean>>;
  /** Set after the first generate; later generates add renders to the same design. */
  designId?: string;
  jobId?: string;
  lastSeed?: number;
  title: string;
  updatedAt: number;
}

interface DraftActions {
  update: (changes: Partial<DraftState>) => void;
  setStyle: (changes: Partial<StyleChoice>) => void;
  setStrokes: (view: ViewName, strokes: Stroke[]) => void;
  setPaper: (view: ViewName, changes: Partial<PaperView>) => void;
  reset: (keep?: Partial<DraftState>) => void;
  hasContent: () => boolean;
}

export const DEFAULT_STYLE: StyleChoice = {
  colour: "camel",
  custom_hex: null,
  print: "plain",
  fabric: "cotton",
  fit: "regular",
  buttons: "default",
  stitching: "tonal",
  scene: "light_room",
  finish: "matte_dark_grey",
  notes: "",
  details: null,
};

export function defaultStyle(catalog: Catalog | null): StyleChoice {
  if (!catalog) return DEFAULT_STYLE;
  return {
    ...DEFAULT_STYLE,
    scene: defaultId(catalog.scenes, DEFAULT_STYLE.scene),
    finish: defaultId(catalog.mannequin_finishes, DEFAULT_STYLE.finish),
  };
}

function emptyDraft(): DraftState {
  return {
    method: "draw",
    group: "women",
    body: "",
    garment: "",
    drawn: {},
    paper: {},
    drawnClean: {},
    style: DEFAULT_STYLE,
    title: "",
    updatedAt: Date.now(),
  };
}

const idbStorage: StateStorage = {
  getItem: async (name) => ((await get(name)) as string | undefined) ?? null,
  setItem: (name, value) => set(name, value),
  removeItem: (name) => del(name),
};

export const useDraft = create<DraftState & DraftActions>()(
  persist(
    (setState, getState) => ({
      ...emptyDraft(),
      update: (changes) => setState({ ...changes, updatedAt: Date.now() }),
      setStyle: (changes) => setState((s) => ({ style: { ...s.style, ...changes }, updatedAt: Date.now() })),
      setStrokes: (view, strokes) =>
        setState((s) => ({ drawn: { ...s.drawn, [view]: { ...s.drawn[view], strokes } }, updatedAt: Date.now() })),
      setPaper: (view, changes) =>
        setState((s) => ({
          paper: { ...s.paper, [view]: { wholeBody: false, ...s.paper[view], ...changes } },
          updatedAt: Date.now(),
        })),
      reset: (keep = {}) => {
        for (const view of ["front", "back", "side"] as ViewName[]) void del(photoKey(view));
        setState({ ...emptyDraft(), ...keep });
      },
      hasContent: () => {
        const s = getState();
        // A reopened design can be re-rendered from the sketches stored on the server.
        if (s.designId) return true;
        return s.method === "draw"
          ? Object.values(s.drawn).some((v) => hasInk(v))
          : Object.values(s.paper).some((v) => v?.cleanId);
      },
    }),
    // skipHydration: IndexedDB only exists in the browser; AuthGate calls rehydrate() on mount.
    {
      name: "draft",
      storage: createJSONStorage(() => idbStorage),
      version: 2,
      skipHydration: true,
      // v1 drafts predate sketch details: start with "not read yet".
      migrate: (persisted) => {
        const state = persisted as DraftState;
        return { ...state, drawnClean: state.drawnClean ?? {}, style: { ...DEFAULT_STYLE, ...state.style } };
      },
    },
  ),
);

/** IndexedDB key of the photo for a view (upload mode). */
export function photoKey(view: ViewName): string {
  return `photo:${view}`;
}

/** Wait for the persisted draft to load before reading it (it's async from IndexedDB). */
export function useDraftHydrated(): boolean {
  return useSyncExternalStore(
    (onChange) => useDraft.persist.onFinishHydration(onChange),
    () => useDraft.persist.hasHydrated(),
    () => false,
  );
}
