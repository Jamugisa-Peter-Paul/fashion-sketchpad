"use client";

import { Plus, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { DesignCard } from "@/components/DesignCard";
import { Button, Notice, Page, Spinner, TopBar } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { DesignSummary } from "@/lib/types";

export default function DesignsPage() {
  const [designs, setDesigns] = useState<DesignSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDesigns(await api.designs());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load designs");
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch on mount; state is set after the await
    void load();
  }, [load]);

  return (
    <>
      <TopBar
        title="My designs"
        back="/"
        right={
          <button type="button" aria-label="Refresh" onClick={() => void load()} className="grid size-11 place-items-center rounded-full active:bg-line/60">
            <RefreshCw className="size-5" />
          </button>
        }
      />
      <Page className="space-y-4">
        {error && <Notice tone="error">{error}</Notice>}
        {!designs && !error && <Spinner />}
        {designs?.length === 0 && (
          <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-line p-10 text-center">
            <p className="text-muted">No designs yet. Your renders are saved here automatically.</p>
            <Link href="/new/">
              <Button icon={<Plus className="size-5" />}>New design</Button>
            </Link>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {designs?.map((design) => <DesignCard key={design.id} design={design} />)}
        </div>
      </Page>
    </>
  );
}
