"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { onUnauthorized } from "@/lib/api";
import { useCatalog } from "@/lib/catalog";
import { useDraft } from "@/lib/draft";
import { loadSettings, signOut } from "@/lib/settings";
import { Spinner } from "./ui";

/** Loads settings and the saved draft, and sends the user to /login when there's no (valid) token. */
export function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  const onLogin = pathname.startsWith("/login");

  useEffect(() => {
    void useDraft.persist.rehydrate();
    return onUnauthorized(() => {
      void signOut().then(() => router.replace("/login/?expired=1"));
    });
  }, [router]);

  useEffect(() => {
    let cancelled = false;
    loadSettings().then(({ token }) => {
      if (cancelled) return;
      if (!token && !onLogin) {
        router.replace("/login/");
        return;
      }
      if (token) void useCatalog.getState().load();
      setReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, [onLogin, router]);

  if (!ready && !onLogin) return <Spinner />;
  return <>{children}</>;
}
