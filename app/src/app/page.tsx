"use client";

import { ArrowRight, Images, PenLine, Plus, Settings } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { DesignCard } from "@/components/DesignCard";
import { Button, Page } from "@/components/ui";
import { api } from "@/lib/api";
import { labelOf, useCatalog } from "@/lib/catalog";
import { defaultStyle, useDraft, useDraftHydrated } from "@/lib/draft";
import type { DesignSummary } from "@/lib/types";

export default function Home() {
  const router = useRouter();
  const hydrated = useDraftHydrated();
  const draft = useDraft();
  const catalog = useCatalog((s) => s.catalog);
  const [recent, setRecent] = useState<DesignSummary[] | null>(null);

  useEffect(() => {
    api.designs().then((designs) => setRecent(designs.slice(0, 4)), () => setRecent([]));
  }, []);

  const hasDraft = hydrated && (draft.hasContent() || !!draft.garment);

  function startNew() {
    draft.reset({ style: defaultStyle(catalog) });
    router.push("/new/");
  }

  return (
    <>
      <header className="safe-top mx-auto flex w-full max-w-6xl items-center justify-between px-4 pt-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Fashion Sketchpad</h1>
          <p className="text-sm text-muted">Sketch it. See it real.</p>
        </div>
        <Link href="/settings/" aria-label="Settings" className="grid size-11 place-items-center rounded-full active:bg-line/60">
          <Settings className="size-6" />
        </Link>
      </header>

      <Page className="space-y-8">
        <div className="grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={startNew}
            className="flex min-h-28 items-center gap-4 rounded-2xl bg-ink p-5 text-left text-white active:opacity-90"
          >
            <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-white/15">
              <Plus className="size-6" />
            </span>
            <span>
              <span className="block text-lg font-semibold">New design</span>
              <span className="text-sm text-white/70">Draw or upload a sketch</span>
            </span>
          </button>

          {hasDraft && (
            <Link
              href={draft.method === "upload" ? "/upload/" : draft.garment ? "/sketch/" : "/new/"}
              className="flex min-h-28 items-center gap-4 rounded-2xl border border-line bg-surface p-5 active:bg-canvas"
            >
              <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent">
                <PenLine className="size-6" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-lg font-semibold">Continue draft</span>
                <span className="block truncate text-sm text-muted">
                  {draft.garment ? labelOf(catalog?.garments, draft.garment) : "Not started"}
                  {draft.designId ? " · saved design" : ""}
                </span>
              </span>
              <ArrowRight className="size-5 text-muted" />
            </Link>
          )}
        </div>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Recent designs</h2>
            <Link href="/designs/" className="flex min-h-11 items-center gap-1 text-sm font-medium text-accent">
              <Images className="size-4" /> All designs
            </Link>
          </div>
          {recent && recent.length === 0 && (
            <p className="rounded-2xl border border-dashed border-line p-6 text-center text-sm text-muted">
              Your renders will appear here.
            </p>
          )}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {recent?.map((design) => <DesignCard key={design.id} design={design} />)}
          </div>
        </section>

        {!hydrated && <Button variant="ghost" loading block />}
      </Page>
    </>
  );
}
