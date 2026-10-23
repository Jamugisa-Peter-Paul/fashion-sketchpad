"use client";

import { Plus, RefreshCw, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Section, Spinner, cx } from "./ui";
import { ApiError, api } from "@/lib/api";
import {
  DETAIL_GROUPS,
  MAX_DETAILS,
  MAX_DETAIL_CHARS,
  addDetail,
  emptyDetails,
  removeDetail,
  type DetailGroup,
} from "@/lib/details";
import { useDraft } from "@/lib/draft";
import { detailsKey, detailsViews } from "@/lib/submit";
import type { SketchDetails } from "@/lib/types";

type Status = { state: "idle" } | { state: "reading" } | { state: "error"; message: string };

/**
 * The construction details the server read off the sketch (buttons, pockets, vents...), as chips. They go
 * into the render prompt so small details aren't lost. Remove wrong ones, add missing ones.
 */
export function DetailsEditor() {
  const draft = useDraft();
  const key = detailsKey(draft);
  const details = draft.style.details ?? null;
  const [status, setStatus] = useState<Status>({ state: "idle" });
  const requested = useRef<string | null>(null);

  async function read(force = false) {
    const state = useDraft.getState();
    const current = detailsKey(state);
    if (!current || (!force && requested.current === current)) return;
    requested.current = current;
    setStatus({ state: "reading" });
    try {
      const response = await api.details(state.garment, await detailsViews(state));
      if (detailsKey(useDraft.getState()) !== current) return; // the sketch changed meanwhile
      if (response.details) {
        useDraft.getState().update({ detailsFor: current });
        useDraft.getState().setStyle({ details: response.details });
        setStatus({ state: "idle" });
      } else {
        setStatus({ state: "error", message: response.error ?? "No details found" });
      }
    } catch (err) {
      setStatus({ state: "error", message: err instanceof ApiError ? err.message : "Could not reach the server" });
    }
  }

  // New or changed sketch: the details on screen belong to another sketch, so read them again.
  useEffect(() => {
    const state = useDraft.getState();
    if (!key) return;
    if (state.style.details && state.detailsFor === key) return;
    if (state.style.details) state.setStyle({ details: null });
    const timer = setTimeout(() => void read(), 0);
    return () => clearTimeout(timer);
  }, [key]);

  function change(next: SketchDetails) {
    useDraft.getState().update({ detailsFor: key || useDraft.getState().detailsFor });
    useDraft.getState().setStyle({ details: next });
  }

  const hint =
    "Read from your sketch and added to the render so small things aren't lost. Remove anything wrong, add what's missing.";
  return (
    <Section title="Sketch details" hint={hint}>
      {status.state === "reading" && !details && <Spinner label="Reading your sketch… (up to a minute the first time)" />}
      {status.state === "error" && (
        <div className="flex items-start justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm">
          <p className="text-muted">
            Couldn&apos;t read the details ({status.message}). The render still follows your sketch; you can add
            details yourself below.
          </p>
          <button
            type="button"
            onClick={() => void read(true)}
            className="grid size-10 shrink-0 place-items-center rounded-full active:bg-line/60"
            aria-label="Try again"
          >
            <RefreshCw className="size-5" />
          </button>
        </div>
      )}
      {!key && !details && (
        <p className="text-sm text-muted">The details are read from the saved sketch when you generate.</p>
      )}
      {(details || status.state === "error" || (!key && !details)) && (
        <div className="space-y-4">
          {DETAIL_GROUPS.map((group) => (
            <DetailRow
              key={group.id}
              label={group.label}
              items={(details ?? emptyDetails())[group.id]}
              onRemove={(item) => change(removeDetail(details ?? emptyDetails(), group.id, item))}
              onAdd={(text) => change(addDetail(details ?? emptyDetails(), group.id as DetailGroup, text))}
            />
          ))}
          {details && key && (
            <button
              type="button"
              onClick={() => void read(true)}
              disabled={status.state === "reading"}
              className="inline-flex items-center gap-2 text-sm font-medium text-muted active:text-ink disabled:opacity-50"
            >
              <RefreshCw className={cx("size-4", status.state === "reading" && "animate-spin")} />
              Read the sketch again
            </button>
          )}
        </div>
      )}
    </Section>
  );
}

function DetailRow({
  label,
  items,
  onRemove,
  onAdd,
}: {
  label: string;
  items: string[];
  onRemove: (item: string) => void;
  onAdd: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const full = items.length >= MAX_DETAILS;
  function submit() {
    if (!text.trim()) return;
    onAdd(text);
    setText("");
  }
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">{label}</p>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <span
            key={item}
            className="inline-flex min-h-10 items-center gap-1 rounded-full border border-line bg-surface pl-4 pr-1 text-sm"
          >
            {item}
            <button
              type="button"
              onClick={() => onRemove(item)}
              aria-label={`Remove ${item}`}
              className="grid size-8 place-items-center rounded-full text-muted active:bg-line/60"
            >
              <X className="size-4" />
            </button>
          </span>
        ))}
        {items.length === 0 && <span className="py-2 text-sm text-muted">None</span>}
      </div>
      {!full && (
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            maxLength={MAX_DETAIL_CHARS}
            placeholder="Add a detail, e.g. two flap pockets"
            className="min-h-11 flex-1 rounded-xl border border-line bg-surface px-3 text-sm outline-none focus:border-ink"
            enterKeyHint="done"
          />
          <button
            type="submit"
            disabled={!text.trim()}
            aria-label={`Add to ${label}`}
            className="grid size-11 place-items-center rounded-xl border border-line bg-surface active:bg-canvas disabled:opacity-40"
          >
            <Plus className="size-5" />
          </button>
        </form>
      )}
    </div>
  );
}
