/**
 * React Native side of connectivity: one NetInfo subscription for the whole app, one slow recovery probe while the
 * CRM is unreachable, and the single banner that tells the person about it.
 */
import { useEffect, useSyncExternalStore } from "react";
import { AppState, Text, View } from "react-native";
import NetInfo from "@react-native-community/netinfo";
import { onlineManager, useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { apiBaseUrl } from "@/api/client";
import { BANNER, connectivity, probeDelayMs, type ConnectivityStatus } from "@/lib/connectivityCore";
import { colors, radius, space } from "@/theme";

export function useConnectivity(): ConnectivityStatus {
  return useSyncExternalStore(connectivity.subscribe, connectivity.getStatus, connectivity.getStatus);
}

let started = false;

/** Call once at startup. Safe to call again (hot reload): it registers the listeners only the first time. */
export function startConnectivity() {
  if (started) return;
  started = true;
  // isConnected only: isInternetReachable relies on a ping to a third-party host and can be wrong on some networks.
  onlineManager.setEventListener((setOnline) =>
    NetInfo.addEventListener((s) => {
      connectivity.setDeviceConnected(s.isConnected !== false);
      setOnline(s.isConnected !== false);
    }),
  );
}

/**
 * While the CRM is unreachable (phone has a network, server does not answer) re-check slowly: 10s, 20s, 40s, then
 * every 60s, only while the app is in the foreground. The first answer clears the banner and refreshes stale screens.
 */
function useRecoveryProbe(status: ConnectivityStatus) {
  const qc = useQueryClient();
  useEffect(() => {
    if (status !== "unreachable") return;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    const schedule = () => {
      timer = setTimeout(async () => {
        if (cancelled) return;
        if (AppState.currentState === "active") {
          const ctl = new AbortController();
          const abort = setTimeout(() => ctl.abort(), 8_000);
          try {
            const res = await fetch(`${apiBaseUrl}/health`, { signal: ctl.signal });
            if (res.ok) {
              connectivity.reportSuccess();
              void qc.invalidateQueries({ refetchType: "active" });
              return;
            }
          } catch {
            /* still unreachable */
          } finally {
            clearTimeout(abort);
          }
        }
        attempt += 1;
        schedule();
      }, probeDelayMs(attempt));
    };
    schedule();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [status, qc]);
}

/** The only place a connectivity problem is announced. Non-blocking, one line, at most one at a time. */
export function ConnectivityBanner() {
  const status = useConnectivity();
  const insets = useSafeAreaInsets();
  useRecoveryProbe(status);
  if (status === "ok") return null;
  return (
    <View pointerEvents="none" style={{ position: "absolute", left: 0, right: 0, top: 0, paddingTop: insets.top + space.xs, paddingHorizontal: space.md, zIndex: 50 }}>
      <View
        accessibilityRole="alert"
        accessibilityLiveRegion="polite"
        style={{ backgroundColor: status === "offline" ? colors.text : colors.warning, borderRadius: radius.md, paddingVertical: space.sm, paddingHorizontal: space.md }}
      >
        <Text style={{ color: colors.white, fontSize: 13, fontWeight: "600", textAlign: "center" }}>{BANNER[status]}</Text>
      </View>
    </View>
  );
}
