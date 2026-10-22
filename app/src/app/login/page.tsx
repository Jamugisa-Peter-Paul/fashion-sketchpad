"use client";

import { KeyRound } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Button, Notice } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useCatalog } from "@/lib/catalog";
import { loadSettings, normaliseUrl, saveSettings } from "@/lib/settings";

function LoginForm() {
  const router = useRouter();
  const expired = useSearchParams().get("expired");
  const [apiUrl, setApiUrl] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadSettings().then((settings) => setApiUrl(settings.apiUrl));
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.testLogin(normaliseUrl(apiUrl), token.trim());
      await saveSettings({ apiUrl, token });
      void useCatalog.getState().load();
      router.replace("/");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "That access code isn't valid."
          : err instanceof ApiError
            ? err.message
            : "Something went wrong.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="safe-top mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-6 py-10">
      <div className="mb-8">
        <div className="mb-4 grid size-14 place-items-center rounded-2xl bg-accent text-white">
          <KeyRound className="size-7" />
        </div>
        <h1 className="text-2xl font-semibold">Fashion Sketchpad</h1>
        <p className="mt-1 text-muted">Enter the access code you were given.</p>
      </div>

      <form onSubmit={submit} className="space-y-4">
        {expired && <Notice tone="warn">Your access code was not accepted. Please sign in again.</Notice>}
        <label className="block">
          <span className="text-sm font-medium">Access code</span>
          <input
            value={token}
            onChange={(e) => setToken(e.target.value)}
            type="password"
            autoComplete="current-password"
            required
            className="mt-1 h-12 w-full rounded-xl border border-line bg-surface px-4 text-base outline-none focus:border-ink"
          />
        </label>
        <details className="rounded-xl border border-line bg-surface px-4 py-3 text-sm">
          <summary className="cursor-pointer font-medium">Server</summary>
          <input
            value={apiUrl}
            onChange={(e) => setApiUrl(e.target.value)}
            inputMode="url"
            placeholder="https://fashion-api.ucu-dct.org"
            className="mt-2 h-11 w-full rounded-lg border border-line px-3 text-base outline-none focus:border-ink"
          />
        </details>
        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" block loading={busy} disabled={!token || !apiUrl}>
          Sign in
        </Button>
      </form>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
