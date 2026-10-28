/**
 * Keeps the app in step with the CRM's daily 10:00 sheet sync (10:00 IST = 04:30 UTC).
 *
 * Everything the app shows is read from the CRM, so nothing needs "cleaning" on the phone. But a phone left open
 * overnight would still be showing yesterday's numbers. Whenever the app comes to the front, if it has not refreshed
 * since the most recent 10:00 sync, it reads everything again. Pull-to-refresh and "Sync now" do the same on request.
 *
 * Entries are the exception: every time the app comes to the front the entry screens (calendars, store lists, "My entries", the admin counts) are
 * read again, so a number corrected, cleared or added in the CRM shows on the phone the next time it is opened, not at the next 10:00.
 */
import { useEffect } from "react";
import { AppState } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useQueryClient } from "@tanstack/react-query";

const KEY = "veekay.lastRefresh";
const SYNC_UTC_MINUTES = 4 * 60 + 30;
const ENTRY_QUERIES = ["s-calendar", "s-stores", "s-my-entries", "a-insights", "a-pending", "a-performance", "a-vendor-performance"];

/** The most recent daily sync time, as epoch ms. */
export function lastSyncBoundary(now = new Date()): number {
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 0, SYNC_UTC_MINUTES);
  return today <= now.getTime() ? today : today - 86_400_000;
}

export function useDailyRefresh(enabled: boolean) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!enabled) return;
    const check = async () => {
      void qc.invalidateQueries({ predicate: (q) => ENTRY_QUERIES.includes(String(q.queryKey[0])) });
      try {
        const last = Number(await AsyncStorage.getItem(KEY)) || 0;
        if (last < lastSyncBoundary()) {
          await qc.invalidateQueries();
          await AsyncStorage.setItem(KEY, String(Date.now()));
        }
      } catch {
        /* storage unavailable: pull-to-refresh still works */
      }
    };
    void check();
    const sub = AppState.addEventListener("change", (s) => { if (s === "active") void check(); });
    return () => sub.remove();
  }, [enabled, qc]);
}

export async function markRefreshed() {
  await AsyncStorage.setItem(KEY, String(Date.now())).catch(() => undefined);
}
