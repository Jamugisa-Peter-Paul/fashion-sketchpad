"use client";

import { get, set } from "idb-keyval";
import { create } from "zustand";
import { api, ApiError } from "./api";
import type { Body, Catalog, Group } from "./types";

// The catalog is cached in IndexedDB so the start screen and drawing work without a connection.

interface CatalogState {
  catalog: Catalog | null;
  offline: boolean;
  error: string | null;
  loading: boolean;
  load: () => Promise<void>;
}

export const useCatalog = create<CatalogState>((setState, getState) => ({
  catalog: null,
  offline: false,
  error: null,
  loading: false,
  async load() {
    if (getState().loading) return;
    setState({ loading: true });
    try {
      const catalog = await api.catalog();
      setState({ catalog, offline: false, error: null });
      await set("catalog", catalog);
    } catch (error) {
      const cached = (await get("catalog")) as Catalog | undefined;
      const message = error instanceof ApiError ? error.message : "Could not load choices";
      setState({ catalog: cached ?? getState().catalog, offline: !!cached, error: message });
    } finally {
      setState({ loading: false });
    }
  },
}));

export const GROUPS: { id: Group; label: string }[] = [
  { id: "women", label: "Women" },
  { id: "men", label: "Men" },
  { id: "kids", label: "Kids" },
];

export function bodiesFor(catalog: Catalog, group: Group): Body[] {
  return catalog.bodies.filter((body) => body.group === group);
}

export function defaultId(items: { id: string; default: boolean }[], fallback: string): string {
  return items.find((item) => item.default)?.id ?? items.find((item) => item.id === fallback)?.id ?? items[0]?.id ?? fallback;
}

export function labelOf(items: { id: string; label: string }[] | undefined, id: string): string {
  return items?.find((item) => item.id === id)?.label ?? id;
}
