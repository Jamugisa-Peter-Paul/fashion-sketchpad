import { Preferences } from "@capacitor/preferences";

// Server URL and token. Preferences is native storage on Android and localStorage in a browser.

export interface Settings {
  apiUrl: string;
  token: string;
}

const DEFAULT_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
let cached: Settings | null = null;

export function normaliseUrl(url: string): string {
  return url.trim().replace(/\/+$/, "");
}

export async function loadSettings(): Promise<Settings> {
  if (cached) return cached;
  const [apiUrl, token] = await Promise.all([Preferences.get({ key: "apiUrl" }), Preferences.get({ key: "token" })]);
  cached = { apiUrl: apiUrl.value || DEFAULT_API_URL, token: token.value || "" };
  return cached;
}

export async function saveSettings(settings: Settings): Promise<void> {
  cached = { apiUrl: normaliseUrl(settings.apiUrl), token: settings.token.trim() };
  await Preferences.set({ key: "apiUrl", value: cached.apiUrl });
  await Preferences.set({ key: "token", value: cached.token });
}

export async function signOut(): Promise<void> {
  const { apiUrl } = await loadSettings();
  cached = { apiUrl, token: "" };
  await Preferences.remove({ key: "token" });
}

export function defaultApiUrl(): string {
  return DEFAULT_API_URL;
}
