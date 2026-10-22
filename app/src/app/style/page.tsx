"use client";

import { Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { StylePicker } from "@/components/StylePicker";
import { BottomBar, Button, Notice, Page, Spinner, TopBar } from "@/components/ui";
import { labelOf, useCatalog } from "@/lib/catalog";
import { useDraft, useDraftHydrated } from "@/lib/draft";

export default function StylePage() {
  const router = useRouter();
  const hydrated = useDraftHydrated();
  const catalog = useCatalog((s) => s.catalog);
  const draft = useDraft();

  if (!hydrated || !catalog) {
    return (
      <>
        <TopBar title="Style" back step={2} />
        <Spinner />
      </>
    );
  }

  const ready = draft.hasContent();
  return (
    <>
      <TopBar
        title={`Style your ${labelOf(catalog.garments, draft.garment).toLowerCase()}`}
        back={draft.method === "draw" ? "/sketch/" : "/upload/"}
        step={2}
      />
      <Page>
        {!ready && <div className="mb-6"><Notice tone="warn">Add a sketch first. Go back to draw or upload one.</Notice></div>}
        <StylePicker catalog={catalog} style={draft.style} onChange={draft.setStyle} />
      </Page>
      <BottomBar>
        <Button block disabled={!ready} icon={<Sparkles className="size-5" />} onClick={() => router.push("/generate/?new=1")}>
          Generate
        </Button>
      </BottomBar>
    </>
  );
}
