"use client";

import { Camera, PenTool } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { BodyThumb } from "@/components/BodyThumb";
import { BottomBar, Button, Chip, Notice, Page, Section, Segmented, Spinner, TopBar, cx } from "@/components/ui";
import { bodiesFor, GROUPS, useCatalog } from "@/lib/catalog";
import { useDraft, useDraftHydrated, type Method } from "@/lib/draft";
import type { Group } from "@/lib/types";

const METHODS: { id: Method; label: string; hint: string; icon: typeof PenTool }[] = [
  { id: "draw", label: "Draw in app", hint: "Sketch over a body outline", icon: PenTool },
  { id: "upload", label: "Upload paper sketch", hint: "Photo of a front (and back)", icon: Camera },
];

export default function StartDesign() {
  const router = useRouter();
  const hydrated = useDraftHydrated();
  const { catalog, error, offline } = useCatalog();
  const draft = useDraft();

  // Pre-select the first generated body of the group so the common case is one tap less.
  const needsBody = hydrated && catalog && !catalog.bodies.some((b) => b.id === draft.body && b.available);
  useEffect(() => {
    if (!needsBody || !catalog) return;
    const first = bodiesFor(catalog, draft.group).find((b) => b.available);
    if (first) draft.update({ body: first.id });
  }, [needsBody, catalog, draft]);

  if (!hydrated || !catalog) {
    return (
      <>
        <TopBar title="New design" back="/" step={0} />
        <Page>{error && !catalog ? <Notice tone="error">{error}</Notice> : <Spinner label="Loading choices" />}</Page>
      </>
    );
  }

  const bodies = bodiesFor(catalog, draft.group);
  const body = catalog.bodies.find((b) => b.id === draft.body && b.available);
  const canContinue = !!body && !!draft.garment;

  function chooseGroup(group: Group) {
    const firstAvailable = bodiesFor(catalog!, group).find((b) => b.available);
    draft.update({ group, body: firstAvailable?.id ?? "" });
  }

  return (
    <>
      <TopBar title="New design" back="/" step={0} />
      <Page className="grid gap-8 md:grid-cols-2 md:gap-10">
        <div className="space-y-8">
          {offline && <Notice tone="warn">Offline: showing saved choices. You can draw now and generate later.</Notice>}

          <Section title="How">
            <div className="grid grid-cols-2 gap-3">
              {METHODS.map(({ id, label, hint, icon: Icon }) => (
                <button
                  key={id}
                  type="button"
                  aria-pressed={draft.method === id}
                  onClick={() => draft.update({ method: id })}
                  className={cx(
                    "flex min-h-32 flex-col items-start justify-between rounded-2xl border-2 p-4 text-left transition-colors",
                    draft.method === id ? "border-ink bg-surface" : "border-transparent bg-surface",
                  )}
                >
                  <Icon className={cx("size-7", draft.method === id ? "text-accent" : "text-muted")} />
                  <span>
                    <span className="block font-semibold">{label}</span>
                    <span className="text-xs text-muted">{hint}</span>
                  </span>
                </button>
              ))}
            </div>
          </Section>

          <Section title="Who">
            <Segmented options={GROUPS} value={draft.group} onChange={chooseGroup} />
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
              {bodies.map((b) => (
                <button
                  key={b.id}
                  type="button"
                  disabled={!b.available}
                  aria-pressed={draft.body === b.id}
                  onClick={() => draft.update({ body: b.id })}
                  className={cx(
                    "flex flex-col items-center rounded-2xl border-2 bg-surface p-2 pb-3 transition-colors",
                    draft.body === b.id ? "border-ink" : "border-transparent",
                    !b.available && "opacity-60",
                  )}
                >
                  <span className="grid h-28 w-full place-items-center">
                    <BodyThumb body={b.id} available={b.available} />
                  </span>
                  <span className="text-sm font-medium">{b.label}</span>
                  {!b.available && <span className="text-[11px] leading-tight text-muted">Not generated yet</span>}
                </button>
              ))}
            </div>
            {bodies.every((b) => !b.available) && (
              <Notice>No {draft.group === "kids" ? "kids'" : draft.group === "men" ? "men's" : "women's"} body templates have been generated on the server yet.</Notice>
            )}
          </Section>
        </div>

        <Section title="What">
          <div className="flex flex-wrap gap-2">
            {catalog.garments.map((g) => (
              <Chip key={g.id} selected={draft.garment === g.id} onClick={() => draft.update({ garment: g.id })}>
                {g.label}
              </Chip>
            ))}
          </div>
        </Section>
      </Page>
      <BottomBar>
        <Button block disabled={!canContinue} onClick={() => router.push(draft.method === "draw" ? "/sketch/" : "/upload/")}>
          {canContinue ? (draft.method === "draw" ? "Start drawing" : "Add photos") : "Choose a body type and garment"}
        </Button>
      </BottomBar>
    </>
  );
}
