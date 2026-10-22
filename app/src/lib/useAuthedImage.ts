"use client";

import { get, set } from "idb-keyval";
import { useEffect, useState } from "react";
import { fetchBlob } from "./api";

/**
 * Object URL for an image behind the token. With `offline`, the blob is also kept in IndexedDB and used
 * when the server can't be reached (body guides, so drawing works without a connection).
 */
export function useAuthedImage(path: string | null | undefined, { offline = false } = {}): {
  url: string | undefined;
  failed: boolean;
} {
  const [state, setState] = useState<{ path?: string; url?: string; failed: boolean }>({ failed: false });

  useEffect(() => {
    if (!path) return;
    let objectUrl: string | undefined;
    let cancelled = false;

    (async () => {
      let blob: Blob | undefined;
      try {
        blob = await fetchBlob(path);
        if (offline) await set(`img:${path}`, blob);
      } catch {
        if (offline) blob = (await get(`img:${path}`)) as Blob | undefined;
      }
      if (cancelled) return;
      if (!blob) {
        setState({ path, failed: true });
        return;
      }
      objectUrl = URL.createObjectURL(blob);
      setState({ path, url: objectUrl, failed: false });
    })();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path, offline]);

  // Ignore a stale result from a previous path while the new one loads.
  return state.path === path ? { url: state.url, failed: state.failed } : { url: undefined, failed: false };
}
