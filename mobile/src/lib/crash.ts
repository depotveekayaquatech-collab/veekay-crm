/**
 * Crash reporting without a third-party service: an uncaught error is sent (best effort, never blocking, at most a few
 * per session) to the Veekay API, which logs it. Native crashes are covered by Google Play's Android vitals.
 */
import Constants from "expo-constants";
import { Platform } from "react-native";
import { apiBaseUrl, configError } from "@/api/client";

let sent = 0;
const seen = new Set<string>();

export async function reportError(error: unknown, opts: { fatal?: boolean; screen?: string } = {}): Promise<void> {
  try {
    if (configError || sent >= 5) return;
    const e = error instanceof Error ? error : new Error(String(error));
    const key = e.message.slice(0, 120);
    if (seen.has(key)) return;
    seen.add(key);
    sent++;
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 8000);
    await fetch(`${apiBaseUrl}/public/client-errors`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        app: "partner-mobile",
        version: Constants.expoConfig?.version ?? "",
        platform: `${Platform.OS} ${Platform.Version}`,
        screen: opts.screen ?? "",
        message: e.message.slice(0, 500) || e.name,
        stack: (e.stack ?? "").slice(0, 4000),
        fatal: !!opts.fatal,
      }),
      signal: ctl.signal,
    }).finally(() => clearTimeout(timer));
  } catch {
    /* reporting must never cause a problem of its own */
  }
}

/** Reports errors nobody caught (the app then behaves as React Native normally would). */
export function installGlobalErrorHandler() {
  const g = globalThis as unknown as { ErrorUtils?: { getGlobalHandler: () => (e: Error, fatal?: boolean) => void; setGlobalHandler: (h: (e: Error, fatal?: boolean) => void) => void } };
  const utils = g.ErrorUtils;
  if (!utils) return;
  const previous = utils.getGlobalHandler();
  utils.setGlobalHandler((e, fatal) => {
    void reportError(e, { fatal });
    previous(e, fatal);
  });
}
