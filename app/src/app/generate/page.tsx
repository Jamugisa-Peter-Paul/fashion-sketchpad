"use client";

import { Download, Home, Loader2, Palette, PenLine, RefreshCw, Share2, Shuffle } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { RenderPanel } from "@/components/RenderPanel";
import { Sheet } from "@/components/Sheet";
import { ColourPicker } from "@/components/StylePicker";
import { Button, Notice, Page, Spinner, TopBar, cx } from "@/components/ui";
import { api, ApiError, fetchBlob } from "@/lib/api";
import { labelOf, useCatalog } from "@/lib/catalog";
import { useDraft, useDraftHydrated, type StyleChoice } from "@/lib/draft";
import { saveImages, shareImages, type ImageFile } from "@/lib/share";
import { isExpiredError, prepareViews, recleanPaper, styleOptions } from "@/lib/submit";
import type { DesignOut, GenerateRequest, JobStatus, ViewName } from "@/lib/types";
import { useAuthedImage } from "@/lib/useAuthedImage";

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
}

function HistoryThumb({ url, selected, onClick, index }: { url?: string; selected: boolean; onClick: () => void; index: number }) {
  const { url: src } = useAuthedImage(url);
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Render ${index}`}
      aria-pressed={selected}
      className={cx("aspect-[832/1216] w-16 shrink-0 overflow-hidden rounded-lg bg-surface", selected ? "ring-2 ring-ink" : "opacity-80")}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- blob URL */}
      {src ? <img src={src} alt="" className="size-full object-cover" /> : <span className="grid size-full place-items-center text-xs text-muted">{index}</span>}
    </button>
  );
}

function GenerateScreen() {
  const router = useRouter();
  const isNew = useSearchParams().get("new") === "1";
  const hydrated = useDraftHydrated();
  const catalog = useCatalog((s) => s.catalog);
  const draft = useDraft();
  const jobId = draft.jobId;

  const [preparing, setPreparing] = useState(isNew);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [etaMax, setEtaMax] = useState<{ jobId: string; value: number }>({ jobId: "", value: 0 });
  const [design, setDesign] = useState<DesignOut | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [colour, setColour] = useState<StyleChoice | null>(null);
  const [viewer, setViewer] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const startedRef = useRef(false);

  /** Queues a render with the current draft style (overridable) and starts watching it. */
  async function generate(request: Partial<GenerateRequest>) {
    const state = useDraft.getState();
    const body: GenerateRequest = { style: styleOptions(state), views: {}, design_id: state.designId, ...request };
    let response;
    try {
      response = await api.generate(body);
    } catch (err) {
      // The design was deleted from the gallery: start a new one (needs the sketches again).
      if (!(err instanceof ApiError && err.status === 404 && body.design_id)) throw err;
      response = await api.generate({ ...body, design_id: undefined, views: await prepareViews(state, catalog!) });
    }
    setJob(null);
    useDraft.getState().update({ designId: response.design_id, jobId: response.job_id });
  }

  // Arriving from the Style screen: upload the sketches and queue the first render (once).
  useEffect(() => {
    if (!isNew || !hydrated || !catalog || startedRef.current) return;
    startedRef.current = true;
    (async () => {
      const state = useDraft.getState();
      try {
        try {
          await generate({ views: await prepareViews(state, catalog) });
        } catch (err) {
          if (!isExpiredError(err) || state.method !== "upload") throw err;
          const ids = await recleanPaper(state);
          for (const [view, cleanId] of Object.entries(ids)) state.setPaper(view as ViewName, { cleanId });
          await generate({ views: await prepareViews(useDraft.getState(), catalog) });
        }
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setPreparing(false);
        router.replace("/generate/"); // so a reload doesn't queue another render
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once per arrival
  }, [isNew, hydrated, catalog, router]);

  // Poll the job every 2 s until it finishes, then load the design for the render history.
  useEffect(() => {
    if (!jobId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const status = await api.job(jobId);
        if (stopped) return;
        setJob(status);
        setEtaMax((m) => ({ jobId: status.id, value: m.jobId === status.id ? Math.max(m.value, status.eta_seconds ?? 0) : (status.eta_seconds ?? 0) }));
        if (status.status === "done" || status.status === "error") {
          api.design(status.design_id).then((d) => !stopped && setDesign(d), () => undefined);
          return;
        }
      } catch (err) {
        if (stopped) return;
        if (err instanceof ApiError && err.status === 404) {
          setError("This render no longer exists.");
          return;
        }
      }
      timer = setTimeout(tick, 2000);
    };
    void tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [jobId]);

  if (!hydrated || !catalog) return <Spinner />;

  const garment = labelOf(catalog.garments, draft.garment);
  const current = job?.id === jobId ? job : null;
  const finished = current?.status === "done" || current?.status === "error";
  const progress =
    current && etaMax.jobId === current.id && etaMax.value > 0 && current.eta_seconds !== null
      ? Math.min(0.97, Math.max(0.03, 1 - current.eta_seconds / etaMax.value))
      : 0.03;
  const views = current ? (Object.keys(current.views) as ViewName[]) : [];
  const doneViews = views.filter((v) => current?.views[v]?.status === "done");

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function imageFiles(): Promise<ImageFile[]> {
    return Promise.all(
      doneViews.map(async (view) => ({
        name: `${draft.garment}-${view}-${current!.seed}.png`,
        blob: await fetchBlob(current!.views[view]!.image_url!),
      })),
    );
  }

  function flash(message: string | null) {
    if (!message) return;
    setToast(message);
    setTimeout(() => setToast(null), 2500);
  }

  return (
    <>
      <TopBar
        title={garment}
        back="/style/"
        step={3}
        right={
          <Link href="/" aria-label="Home" className="grid size-11 place-items-center rounded-full active:bg-line/60">
            <Home className="size-5" />
          </Link>
        }
      />
      <Page className="mx-auto max-w-4xl space-y-5">
        {error && <Notice tone="error">{error}</Notice>}

        {preparing ? (
          <Spinner label="Uploading your sketch…" />
        ) : !jobId ? (
          <Notice>
            Nothing is rendering. <Link href="/style/" className="font-semibold underline">Go to Style</Link> and tap Generate.
          </Notice>
        ) : !current ? (
          <Spinner label="Checking progress…" />
        ) : (
          <>
            <p className="flex min-h-6 items-center gap-2 text-sm text-muted">
              {!finished && <Loader2 className="size-4 animate-spin" />}
              {current.status === "queued" && current.position
                ? `Waiting for ${current.position} other render${current.position === 1 ? "" : "s"}…`
                : current.status === "queued" || current.status === "running"
                  ? `Rendering… about ${Math.max(5, current.eta_seconds ?? 60)} s left`
                  : current.status === "done"
                    ? `Done · seed ${current.seed}`
                    : "Some views failed. Try again, or change the sketch."}
            </p>

            <div className={cx("grid gap-3", views.length > 2 ? "grid-cols-3" : "grid-cols-2")}>
              {views.map((view) => (
                <RenderPanel
                  key={view}
                  view={view}
                  status={current.views[view]!.status}
                  imageUrl={current.views[view]!.image_url}
                  error={current.views[view]!.error}
                  sketchUrl={`/api/designs/${current.design_id}/sketch/${view}.png`}
                  progress={current.views[view]!.status === "queued" ? 0 : progress}
                  onOpen={setViewer}
                />
              ))}
            </div>

            {finished && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <Button
                    icon={<Shuffle className="size-5" />}
                    loading={busy === "variation"}
                    onClick={() => run("variation", () => generate({}))}
                  >
                    New variation
                  </Button>
                  <Button variant="secondary" icon={<Palette className="size-5" />} onClick={() => setColour(draft.style)}>
                    Change colour
                  </Button>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <Button variant="secondary" icon={<PenLine className="size-5" />} onClick={() => router.push(draft.method === "draw" ? "/sketch/" : "/upload/")}>
                    Edit
                  </Button>
                  <Button
                    variant="secondary"
                    icon={<Download className="size-5" />}
                    disabled={!doneViews.length}
                    loading={busy === "save"}
                    onClick={() => run("save", async () => flash(await saveImages(await imageFiles())))}
                  >
                    Save
                  </Button>
                  <Button
                    variant="secondary"
                    icon={<Share2 className="size-5" />}
                    disabled={!doneViews.length}
                    loading={busy === "share"}
                    onClick={() => run("share", async () => flash(await shareImages(await imageFiles(), garment)))}
                  >
                    Share
                  </Button>
                </div>
                {current.status === "error" && (
                  <Button
                    variant="ghost"
                    block
                    icon={<RefreshCw className="size-5" />}
                    loading={busy === "retry"}
                    onClick={() => run("retry", () => generate({ seed: current.seed }))}
                  >
                    Try again with the same seed
                  </Button>
                )}
              </div>
            )}

            {design && design.renders.length > 1 && (
              <section className="space-y-2">
                <h2 className="text-sm font-semibold text-muted">All renders of this design</h2>
                <div className="flex gap-2 overflow-x-auto pb-1">
                  {[...design.renders].reverse().map((render, i) => (
                    <HistoryThumb
                      key={render.id}
                      index={design.renders.length - i}
                      url={Object.values(render.image_urls)[0]}
                      selected={render.id === jobId}
                      onClick={() => draft.update({ jobId: render.id })}
                    />
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </Page>

      <Sheet
        title="Change colour"
        open={!!colour}
        onClose={() => setColour(null)}
        footer={
          <Button
            block
            loading={busy === "colour"}
            onClick={() =>
              run("colour", async () => {
                draft.setStyle({ colour: colour!.colour, custom_hex: colour!.custom_hex, print: colour!.print });
                await generate({ seed: current?.seed });
                setColour(null);
              })
            }
          >
            Render in this colour
          </Button>
        }
      >
        {colour && <ColourPicker catalog={catalog} style={colour} onChange={(c) => setColour({ ...colour, ...c })} />}
        <p className="mt-4 text-xs text-muted">Uses the same seed, so the garment stays close to this render.</p>
      </Sheet>

      {viewer && (
        <button type="button" className="fixed inset-0 z-50 bg-black" onClick={() => setViewer(null)} aria-label="Close">
          {/* eslint-disable-next-line @next/next/no-img-element -- blob URL */}
          <img src={viewer} alt="" className="size-full object-contain" />
        </button>
      )}
      {toast && (
        <div className="safe-bottom pointer-events-none fixed inset-x-0 bottom-4 z-50 flex justify-center">
          <span className="rounded-full bg-ink px-4 py-2 text-sm text-white shadow-lg">{toast}</span>
        </div>
      )}
    </>
  );
}

export default function GeneratePage() {
  return (
    <Suspense fallback={<Spinner />}>
      <GenerateScreen />
    </Suspense>
  );
}
