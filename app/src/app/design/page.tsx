"use client";

import { Check, Pencil, Share2, Sparkles, Trash2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { RenderPanel } from "@/components/RenderPanel";
import { Button, Notice, Page, Section, Spinner, TopBar, cx } from "@/components/ui";
import { api, ApiError, fetchBlob } from "@/lib/api";
import { labelOf, useCatalog } from "@/lib/catalog";
import { useDraft } from "@/lib/draft";
import { openDesign } from "@/lib/openDesign";
import { shareImages } from "@/lib/share";
import type { DesignOut, RenderOut, ViewName } from "@/lib/types";

function choiceSummary(design: DesignOut, render: RenderOut, catalog: ReturnType<typeof useCatalog.getState>["catalog"]): string {
  const s = render.style;
  const colour = s.custom_hex ?? labelOf(catalog?.colours, s.colour);
  const print = s.print === "plain" ? "" : ` ${labelOf(catalog?.prints, s.print).toLowerCase()}`;
  return `${colour}${print} · ${labelOf(catalog?.fabrics, s.fabric)} · ${labelOf(catalog?.scenes, s.scene)}`;
}

function DesignScreen() {
  const router = useRouter();
  const id = useSearchParams().get("id") ?? "";
  const catalog = useCatalog((s) => s.catalog);
  const [design, setDesign] = useState<DesignOut | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    api.design(id).then(setDesign, (err) => setError(err instanceof ApiError ? err.message : "Could not load the design"));
  }, [id]);

  if (error) {
    return (
      <>
        <TopBar title="Design" back="/designs/" />
        <Page>
          <Notice tone="error">{error}</Notice>
        </Page>
      </>
    );
  }
  if (!design) return <Spinner />;

  const renders = [...design.renders].reverse();
  const render = renders.find((r) => r.id === selected) ?? renders.find((r) => r.status === "done") ?? renders[0];
  const name = design.title || labelOf(catalog?.garments, design.style.garment);
  const views = render ? (Object.keys(render.views) as ViewName[]) : [];

  async function reopen(target: "style" | "sketch") {
    setBusy(target);
    try {
      const method = await openDesign(design!, catalog);
      if (render) useDraft.getState().update({ jobId: render.id, style: { ...useDraft.getState().style, ...render.style } });
      router.push(target === "style" ? "/style/" : method === "draw" ? "/sketch/" : "/upload/");
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    if (!window.confirm(`Delete "${name}" and all its renders?`)) return;
    await api.deleteDesign(design!.id);
    const draft = useDraft.getState();
    if (draft.designId === design!.id) draft.update({ designId: undefined, jobId: undefined });
    router.replace("/designs/");
  }

  async function saveTitle() {
    if (title === null) return;
    setDesign(await api.renameDesign(design!.id, title.trim()));
    setTitle(null);
  }

  return (
    <>
      <TopBar title={name} back="/designs/" />
      <Page className="mx-auto max-w-4xl space-y-6">
        <div className="flex items-center gap-2">
          {title === null ? (
            <button type="button" onClick={() => setTitle(design.title)} className="flex min-h-11 items-center gap-2 text-left text-xl font-semibold">
              {name} <Pencil className="size-4 text-muted" />
            </button>
          ) : (
            <form
              className="flex flex-1 gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void saveTitle();
              }}
            >
              <input
                autoFocus
                value={title}
                maxLength={80}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={labelOf(catalog?.garments, design.style.garment)}
                className="h-11 flex-1 rounded-xl border border-line bg-surface px-3 text-base outline-none focus:border-ink"
              />
              <Button type="submit" icon={<Check className="size-5" />} aria-label="Save name" />
            </form>
          )}
        </div>

        {render && (
          <>
            <p className="text-sm text-muted">{choiceSummary(design, render, catalog)} · seed {render.seed}</p>
            <div className={cx("grid gap-3", views.length > 2 ? "grid-cols-3" : "grid-cols-2")}>
              {views.map((view) => (
                <RenderPanel
                  key={view}
                  view={view}
                  status={render.views[view]!.status}
                  error={render.views[view]!.error}
                  imageUrl={render.image_urls[view]}
                  sketchUrl={design.sketch_urls[view]}
                />
              ))}
            </div>
          </>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Button icon={<Sparkles className="size-5" />} loading={busy === "style"} onClick={() => reopen("style")}>
            Tweak style
          </Button>
          <Button variant="secondary" icon={<Pencil className="size-5" />} loading={busy === "sketch"} onClick={() => reopen("sketch")}>
            Edit sketch
          </Button>
          <Button
            variant="secondary"
            icon={<Share2 className="size-5" />}
            disabled={!render || !Object.keys(render.image_urls).length}
            onClick={async () => {
              const files = await Promise.all(
                Object.entries(render!.image_urls).map(async ([view, url]) => ({ name: `${design.style.garment}-${view}-${render!.seed}.png`, blob: await fetchBlob(url!) })),
              );
              await shareImages(files, name);
            }}
          >
            Share
          </Button>
          <Button variant="danger" icon={<Trash2 className="size-5" />} onClick={remove}>
            Delete
          </Button>
        </div>

        {renders.length > 1 && (
          <Section title={`All renders (${renders.length})`}>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6">
              {renders.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => setSelected(r.id)}
                  aria-pressed={r.id === render?.id}
                  className={cx("rounded-xl p-1 text-left", r.id === render?.id ? "bg-ink/10 ring-2 ring-ink" : "")}
                >
                  <RenderThumb render={r} />
                  <span className="block truncate px-1 pt-1 text-[11px] text-muted">{r.style.custom_hex ?? labelOf(catalog?.colours, r.style.colour)}</span>
                </button>
              ))}
            </div>
          </Section>
        )}
      </Page>
    </>
  );
}

function RenderThumb({ render }: { render: RenderOut }) {
  const view = (Object.keys(render.image_urls)[0] ?? "front") as ViewName;
  return (
    <div className="pointer-events-none">
      <RenderPanel view={view} status={render.views[view]?.status ?? render.status} imageUrl={render.image_urls[view]} error={null} caption={false} />
    </div>
  );
}

export default function DesignPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <DesignScreen />
    </Suspense>
  );
}
