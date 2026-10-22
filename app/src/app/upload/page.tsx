"use client";

import { Camera, ImagePlus, PersonStanding, RefreshCw, Trash2 } from "lucide-react";
import { del, get, set } from "idb-keyval";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { guidePath } from "@/components/BodyThumb";
import { PlacementEditor } from "@/components/PlacementEditor";
import { BottomBar, Button, Notice, Spinner, TopBar, cx } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { labelOf, useCatalog } from "@/lib/catalog";
import { photoKey, useDraft, useDraftHydrated } from "@/lib/draft";
import { downscalePhoto } from "@/lib/images";
import { VIEW_LABELS, type ViewName } from "@/lib/types";
import { useAuthedImage } from "@/lib/useAuthedImage";

const VIEWS: ViewName[] = ["front", "back"];

export default function UploadPage() {
  const router = useRouter();
  const hydrated = useDraftHydrated();
  const catalog = useCatalog((s) => s.catalog);
  const draft = useDraft();
  const [view, setView] = useState<ViewName>("front");
  const [busy, setBusy] = useState<ViewName | null>(null);
  const [errors, setErrors] = useState<Partial<Record<ViewName, string>>>({});
  const cameraInput = useRef<HTMLInputElement>(null);
  const galleryInput = useRef<HTMLInputElement>(null);

  const paper = draft.paper[view];
  const scene = catalog?.scenes.find((s) => s.id === draft.style.scene);
  const onMannequin = scene?.on_mannequin !== false;
  const kind = onMannequin ? "mannequin" : "product";
  const { url: overlayUrl, failed: overlayFailed } = useAuthedImage(paper?.cleanId ? `/api/sketch/${paper.cleanId}/overlay.png` : null);
  const { url: guideUrl } = useAuthedImage(onMannequin && draft.body ? guidePath(draft.body, view) : null, { offline: true });
  const missingChoices = hydrated && (!draft.body || !draft.garment);

  useEffect(() => {
    if (missingChoices) router.replace("/new/");
  }, [missingChoices, router]);

  if (!hydrated || missingChoices) return <Spinner />;

  async function clean(target: ViewName, photo: Blob, wholeBody: boolean) {
    setBusy(target);
    setErrors((e) => ({ ...e, [target]: undefined }));
    try {
      const form = new FormData();
      form.append("image", photo, "sketch.jpg");
      form.append("source", "paper");
      form.append("scene", draft.style.scene);
      form.append("garment", draft.garment);
      form.append("body", draft.body);
      form.append("view", target);
      form.append("whole_body", String(wholeBody));
      const result = await api.clean(form);
      draft.setPaper(target, {
        cleanId: result.clean_id,
        width: result.width,
        height: result.height,
        placement: result.placement,
        suggested: result.placement,
        wholeBody,
        cleanedFor: kind,
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Could not process the photo.";
      setErrors((e) => ({ ...e, [target]: message }));
    } finally {
      setBusy(null);
    }
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    const target = view;
    try {
      const photo = await downscalePhoto(file);
      await set(photoKey(target), photo);
      await clean(target, photo, draft.paper[target]?.wholeBody ?? false);
    } catch {
      setErrors((e) => ({ ...e, [target]: "That file couldn't be opened as a photo." }));
    }
  }

  async function reclean(wholeBody: boolean) {
    const photo = (await get(photoKey(view))) as Blob | undefined;
    if (photo) await clean(view, photo, wholeBody);
  }

  async function remove() {
    await del(photoKey(view));
    const next = { ...draft.paper };
    delete next[view];
    draft.update({ paper: next });
  }

  const anyCleaned = VIEWS.some((v) => draft.paper[v]?.cleanId);
  const error = errors[view];

  return (
    <div className="flex h-dvh flex-col">
      <TopBar title={`Upload your ${labelOf(catalog?.garments, draft.garment).toLowerCase()} sketch`} back="/new/" step={1} />

      <div className="mx-auto flex w-full max-w-3xl gap-2 px-4 pt-3" role="tablist">
        {VIEWS.map((v) => (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={view === v}
            onClick={() => setView(v)}
            className={cx(
              "flex min-h-10 items-center gap-2 rounded-full px-4 text-sm font-medium",
              view === v ? "bg-ink text-white" : "bg-surface text-ink",
            )}
          >
            {VIEW_LABELS[v]}
            {draft.paper[v]?.cleanId && <span className={cx("size-1.5 rounded-full", view === v ? "bg-white" : "bg-accent")} />}
          </button>
        ))}
        {view === "back" && <span className="ml-auto self-center text-xs text-muted">Optional</span>}
      </div>

      <main className="mx-auto flex min-h-0 w-full max-w-3xl flex-1 flex-col gap-3 px-4 py-3">
        {error && <Notice tone="error">{error}</Notice>}

        {busy === view ? (
          <div className="grid flex-1 place-items-center">
            <Spinner label="Cleaning up your sketch…" />
          </div>
        ) : paper?.cleanId && paper.placement && paper.width && paper.height ? (
          <>
            {paper.cleanedFor !== kind && (
              <Notice tone="warn">
                The scene changed since this photo was added.{" "}
                <button type="button" className="font-semibold underline" onClick={() => reclean(paper.wholeBody)}>
                  Update preview
                </button>
              </Notice>
            )}
            {overlayFailed && <Notice tone="warn">This cleaned sketch has expired on the server. Please add the photo again.</Notice>}
            <div className="min-h-0 flex-1">
              <PlacementEditor
                overlayUrl={overlayUrl}
                guideUrl={guideUrl}
                width={paper.width}
                height={paper.height}
                placement={paper.placement}
                suggested={paper.suggested}
                locked={!onMannequin}
                onChange={(placement) => draft.setPaper(view, { placement })}
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" icon={<Camera className="size-5" />} onClick={() => cameraInput.current?.click()}>
                Retake
              </Button>
              {onMannequin && (
                <Button
                  variant={paper.wholeBody ? "primary" : "secondary"}
                  icon={<PersonStanding className="size-5" />}
                  onClick={() => reclean(!paper.wholeBody)}
                  aria-pressed={paper.wholeBody}
                >
                  Sketch shows whole body
                </Button>
              )}
              <Button variant="ghost" icon={<Trash2 className="size-5" />} onClick={remove} aria-label="Remove photo" />
            </div>
          </>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-6 rounded-2xl border-2 border-dashed border-line px-6 py-8 text-center">
            <div>
              <p className="text-lg font-semibold">Add a photo of the {view} of your sketch</p>
              <p className="mt-1 text-sm text-muted">
                Lay the paper flat in good light and fill the frame. Notes and labels next to the drawing are removed automatically.
              </p>
            </div>
            <div className="flex w-full max-w-sm flex-col gap-3">
              <Button block icon={<Camera className="size-5" />} onClick={() => cameraInput.current?.click()}>
                Take photo
              </Button>
              <Button block variant="secondary" icon={<ImagePlus className="size-5" />} onClick={() => galleryInput.current?.click()}>
                Choose from gallery
              </Button>
            </div>
            {error && (
              <Button variant="ghost" icon={<RefreshCw className="size-5" />} onClick={() => reclean(paper?.wholeBody ?? false)}>
                Try again
              </Button>
            )}
          </div>
        )}

        <input
          ref={cameraInput}
          type="file"
          accept="image/*"
          capture="environment"
          hidden
          onChange={(e) => {
            void onFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <input
          ref={galleryInput}
          type="file"
          accept="image/*"
          hidden
          onChange={(e) => {
            void onFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </main>

      <BottomBar>
        <Button block disabled={!anyCleaned || busy !== null} onClick={() => router.push("/style/")}>
          {anyCleaned ? "Next: style" : "Add at least the front"}
        </Button>
      </BottomBar>
    </div>
  );
}
