"use client";

import { LogOut, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Notice, Page, Section, TopBar } from "@/components/ui";
import { useCatalog } from "@/lib/catalog";
import { defaultStyle, useDraft } from "@/lib/draft";
import { loadSettings, signOut } from "@/lib/settings";

export default function SettingsPage() {
  const router = useRouter();
  const [apiUrl, setApiUrl] = useState("");
  const [cleared, setCleared] = useState(false);
  const { catalog, offline, error } = useCatalog();

  useEffect(() => {
    loadSettings().then((s) => setApiUrl(s.apiUrl));
  }, []);

  return (
    <>
      <TopBar title="Settings" back="/" />
      <Page className="max-w-xl space-y-8">
        <Section title="Server">
          <p className="break-all rounded-xl border border-line bg-surface px-4 py-3 text-sm">{apiUrl || "Not set"}</p>
          {offline && <Notice tone="warn">Can&apos;t reach the server right now. {error}</Notice>}
          {catalog && !offline && (
            <p className="text-sm text-muted">
              Connected · {catalog.bodies.filter((b) => b.available).length} of {catalog.bodies.length} body types generated
            </p>
          )}
        </Section>

        <Section title="Draft" hint="Removes the sketch you're working on from this device. Saved designs are not affected.">
          <Button
            variant="secondary"
            icon={<Trash2 className="size-5" />}
            onClick={() => {
              useDraft.getState().reset({ style: defaultStyle(catalog) });
              setCleared(true);
            }}
          >
            {cleared ? "Draft cleared" : "Clear draft"}
          </Button>
        </Section>

        <Section title="Account">
          <Button
            variant="danger"
            icon={<LogOut className="size-5" />}
            onClick={async () => {
              await signOut();
              router.replace("/login/");
            }}
          >
            Sign out
          </Button>
        </Section>
      </Page>
    </>
  );
}
