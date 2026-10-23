// Mirrors the gateway's pydantic models (gateway/models.py, gateway/catalog.py).

export type ViewName = "front" | "back" | "side";
export type Group = "women" | "men" | "kids";
export type ViewStatus = "queued" | "running" | "done" | "error";
export type Source = "paper" | "drawn";

export interface Choice {
  id: string;
  label: string;
  prompt: string;
  default: boolean;
}
export interface Garment extends Choice {
  placement: "top" | "bottom" | "full";
  back?: string;
  legs?: boolean;
}
export interface Colour extends Choice {
  hex: string;
}
export interface Scene extends Choice {
  on_mannequin: boolean;
}
export interface Body extends Choice {
  group: Group;
  views: ViewName[];
  available: boolean;
}

export interface Catalog {
  garments: Garment[];
  fabrics: Choice[];
  colours: Colour[];
  prints: Choice[];
  fits: Choice[];
  buttons: Choice[];
  stitching: Choice[];
  scenes: Scene[];
  mannequin_finishes: Choice[];
  bodies: Body[];
}

export interface Placement {
  cx: number;
  cy: number;
  scale: number;
}

export interface CleanResponse {
  clean_id: string;
  source: Source;
  width: number;
  height: number;
  placement: Placement;
  lines_url: string;
  overlay_url: string;
}

export interface StyleOptions {
  garment: string;
  body: string;
  colour: string;
  custom_hex: string | null;
  print: string;
  fabric: string;
  fit: string;
  buttons: string;
  stitching: string;
  scene: string;
  finish: string;
  notes: string;
  /** Construction details per view; null = let the gateway read them off the sketch at render time. */
  details?: SketchDetails | null;
}

/** Construction details read off the sketch (gateway/details.py). */
export interface SketchDetails {
  garment: string[];
  front: string[];
  back: string[];
  side: string[];
}

export interface DetailsResponse {
  details: SketchDetails | null;
  /** Why the details couldn't be read (the render still works without them). */
  error: string | null;
}

export interface GenerateRequest {
  design_id?: string;
  title?: string;
  style: StyleOptions;
  views: Partial<Record<ViewName, { clean_id: string; placement?: Placement }>>;
  seed?: number;
}

export interface JobStatus {
  id: string;
  design_id: string;
  status: ViewStatus;
  seed: number;
  position: number | null;
  eta_seconds: number | null;
  views: Partial<Record<ViewName, { status: ViewStatus; error: string | null; image_url: string | null }>>;
  details?: SketchDetails | null;
}

export interface DesignSummary {
  id: string;
  title: string;
  garment: string;
  body: string;
  updated_at: number;
  render_count: number;
  thumbnail_url: string | null;
}

export interface RenderOut {
  id: string;
  seed: number;
  style: StyleOptions;
  views: Partial<Record<ViewName, { status: ViewStatus; error: string | null }>>;
  created_at: number;
  status: ViewStatus;
  image_urls: Partial<Record<ViewName, string>>;
  details?: SketchDetails | null;
}

export interface DesignOut {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  style: StyleOptions;
  views: Partial<Record<ViewName, { source: Source; placement: Placement | null; width: number; height: number }>>;
  renders: RenderOut[];
  sketch_urls: Partial<Record<ViewName, string>>;
  lines_urls: Partial<Record<ViewName, string>>;
}

export const CANVAS_W = 832;
export const CANVAS_H = 1216;
export const VIEW_LABELS: Record<ViewName, string> = { front: "Front", back: "Back", side: "Side" };
