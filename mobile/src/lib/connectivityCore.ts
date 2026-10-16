/**
 * The single source of truth for "can this phone reach the CRM". Pure logic (no React Native imports) so it can be
 * unit-tested with node:test; connectivity.ts wires it to NetInfo and the UI.
 *
 * Three states, kept apart on purpose:
 *   ok          - nothing wrong that we know of
 *   offline     - the phone reports no network (debounced, so a Wi-Fi <-> mobile-data switch does not flash a banner)
 *   unreachable - the phone has a network, but several requests in a row could not reach the CRM server
 */

export type FailureKind = "offline" | "unreachable" | "timeout";
export type ConnectivityStatus = "ok" | "offline" | "unreachable";

export const MESSAGES = {
  offline: "No internet connection. Check your network and try again.",
  unreachable: "Unable to reach Veekay CRM servers. Please try again in a moment.",
  timeout: "The server took too long to answer. Please try again.",
} as const;

/** Banner wording per status. */
export const BANNER: Record<Exclude<ConnectivityStatus, "ok">, string> = {
  offline: "You're offline. Changes you make are kept on this phone where possible.",
  unreachable: "Unable to reach Veekay CRM servers. Retrying…",
};

export const OFFLINE_DEBOUNCE_MS = 2_500;
export const FAILURE_WINDOW_MS = 60_000;
export const FAILURES_BEFORE_BANNER = 2;

export interface Clock {
  now(): number;
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

const realClock: Clock = {
  now: () => Date.now(),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
};

export function createConnectivity(clock: Clock = realClock) {
  let deviceConnected = true; // NetInfo reports the real value as soon as it is subscribed
  let status: ConnectivityStatus = "ok";
  let failures: number[] = [];
  let offlineTimer: unknown = null;
  const listeners = new Set<() => void>();

  const set = (next: ConnectivityStatus) => {
    if (next === status) return;
    status = next;
    listeners.forEach((l) => l());
  };

  return {
    getStatus: () => status,
    /** True when the phone itself says it has no network. Used to word a failed request correctly. */
    isDeviceOffline: () => !deviceConnected,
    subscribe(l: () => void) {
      listeners.add(l);
      return () => {
        listeners.delete(l);
      };
    },

    /** Called by the NetInfo listener. Going offline only counts once it lasts; coming back clears everything. */
    setDeviceConnected(connected: boolean) {
      deviceConnected = connected;
      if (connected) {
        if (offlineTimer !== null) clock.clearTimeout(offlineTimer);
        offlineTimer = null;
        failures = [];
        set("ok");
      } else if (offlineTimer === null && status !== "offline") {
        offlineTimer = clock.setTimeout(() => {
          offlineTimer = null;
          if (!deviceConnected) set("offline");
        }, OFFLINE_DEBOUNCE_MS);
      }
    },

    /** A request could not reach the server. Repeated failures while the phone has a network mean the CRM is unreachable. */
    reportFailure(kind: FailureKind) {
      if (kind === "offline") return; // the NetInfo path owns the offline state
      const t = clock.now();
      failures = failures.filter((x) => t - x < FAILURE_WINDOW_MS);
      failures.push(t);
      if (deviceConnected && failures.length >= FAILURES_BEFORE_BANNER) set("unreachable");
    },

    /** Any response from the server (even an error status) proves both the phone and the server are reachable. */
    reportSuccess() {
      failures = [];
      if (status !== "ok") {
        deviceConnected = true; // a response arrived, so NetInfo was lagging if it said offline
        set("ok");
      }
    },
  };
}

export type Connectivity = ReturnType<typeof createConnectivity>;

/** True for the three messages above: lets lists show a short inline note instead of repeating the banner text. */
export function isConnectivityMessage(message: string): boolean {
  return message === MESSAGES.offline || message === MESSAGES.unreachable || message === MESSAGES.timeout;
}

/** Wait before probe number `attempt` (0-based) while the CRM is unreachable: 10s, 20s, 40s, then every 60s. */
export function probeDelayMs(attempt: number): number {
  return Math.min(60_000, 10_000 * 2 ** attempt);
}

/**
 * Only idempotent reads are retried automatically, and only for failures that can clear by themselves.
 * Mutations never go through this (React Query's default for mutations is no retry).
 */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (failureCount >= 2) return false;
  const status = typeof error === "object" && error && "status" in error ? Number((error as { status: unknown }).status) : NaN;
  if (status === 0) return true; // no network / unreachable / timeout
  if (status === 502 || status === 503 || status === 504) return true;
  return false; // 401/403/404/422/429/other 5xx: retrying immediately does not help (429 would make it worse)
}

/** The one shared instance for the whole app. */
export const connectivity = createConnectivity();
