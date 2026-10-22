import { loadSettings } from "./settings";
import type {
  Catalog,
  CleanResponse,
  DesignOut,
  DesignSummary,
  GenerateRequest,
  JobStatus,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Listeners are told when the server rejects the token, so the app can send the user to login. */
const unauthorizedListeners = new Set<() => void>();
export function onUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

function detailMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: string; loc?: string[] };
    return [first.loc?.slice(1).join("."), first.msg].filter(Boolean).join(": ");
  }
  return fallback;
}

async function rawFetch(path: string, init: RequestInit = {}, override?: { apiUrl: string; token: string }) {
  const { apiUrl, token } = override ?? (await loadSettings());
  if (!apiUrl) throw new ApiError(0, "No server set. Open Settings and enter the server address.");
  let response: Response;
  try {
    response = await fetch(apiUrl + path, {
      ...init,
      headers: { ...init.headers, Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your internet connection.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    if (response.status === 401 && !override) unauthorizedListeners.forEach((listener) => listener());
    throw new ApiError(response.status, detailMessage(body, `Server error (${response.status})`));
  }
  return response;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await rawFetch(path, init);
  return (response.status === 204 ? undefined : await response.json()) as T;
}

function post<T>(path: string, body: unknown, method = "POST"): Promise<T> {
  return json<T>(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

export const api = {
  /** Checks a server + token pair before saving them (login screen). */
  async testLogin(apiUrl: string, token: string): Promise<void> {
    await rawFetch("/api/catalog", {}, { apiUrl, token });
  },
  catalog: () => json<Catalog>("/api/catalog"),
  clean: (form: FormData) => json<CleanResponse>("/api/sketch/clean", { method: "POST", body: form }),
  generate: (request: GenerateRequest) => post<{ job_id: string; design_id: string }>("/api/generate", request),
  job: (id: string) => json<JobStatus>(`/api/jobs/${id}`),
  designs: () => json<DesignSummary[]>("/api/designs"),
  design: (id: string) => json<DesignOut>(`/api/designs/${id}`),
  renameDesign: (id: string, title: string) => post<DesignOut>(`/api/designs/${id}`, { title }, "PATCH"),
  deleteDesign: (id: string) => json<void>(`/api/designs/${id}`, { method: "DELETE" }),
};

const blobCache = new Map<string, Promise<Blob>>();

/** Images are behind the token too, so they're fetched as blobs (renders never change once written). */
export function fetchBlob(path: string, { cache = true } = {}): Promise<Blob> {
  const hit = cache ? blobCache.get(path) : undefined;
  if (hit) return hit;
  const pending = rawFetch(path).then((response) => response.blob());
  if (cache) {
    blobCache.set(path, pending);
    pending.catch(() => blobCache.delete(path));
  }
  return pending;
}
