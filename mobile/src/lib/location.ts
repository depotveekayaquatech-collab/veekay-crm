/**
 * The phone's position at the moment of check in / out. Asked only when the person taps the button, never in the
 * background. Indoors a single high-accuracy GPS request often never answers, so this tries in stages:
 *   1. permission (asked once, with a plain-language reason; "blocked" when Android will not ask again)
 *   2. the phone's Location switch (offers Android's one-tap "turn on location" dialog)
 *   3. a balanced fix (Wi-Fi / mobile network + GPS: fast indoors)
 *   4. the last position the phone knew (up to 10 minutes old)
 *   5. a high-accuracy GPS fix
 * and reports exactly which step failed, so the screen can say what to do.
 */
import { Alert } from "react-native";
import * as Location from "expo-location";
import type { Reading } from "@/api/staff";

export type LocationFailure = "denied" | "blocked" | "services_off" | "unavailable";
export type LocationResult = { reading: Reading } | { skipped: LocationFailure };

const BALANCED_MS = 12_000;
const GPS_MS = 12_000;
const LAST_KNOWN_MAX_AGE_MS = 10 * 60_000;

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T | null> {
  return new Promise((resolve) => {
    const t = setTimeout(() => resolve(null), ms);
    p.then(
      (v) => { clearTimeout(t); resolve(v); },
      () => { clearTimeout(t); resolve(null); },
    );
  });
}

const toReading = (p: Location.LocationObject): Reading => ({
  latitude: p.coords.latitude,
  longitude: p.coords.longitude,
  accuracy: p.coords.accuracy ?? undefined,
});

export async function readLocation(): Promise<LocationResult> {
  // 1. permission
  let perm = await Location.getForegroundPermissionsAsync();
  if (!perm.granted && perm.canAskAgain) {
    await new Promise<void>((resolve) =>
      Alert.alert("Share your location?", "Veekay uses your location only at the moment you check in or out, to record where you were. It is never tracked in the background.", [{ text: "Continue", onPress: () => resolve() }]),
    );
    perm = await Location.requestForegroundPermissionsAsync();
  }
  if (!perm.granted) return { skipped: perm.canAskAgain ? "denied" : "blocked" };

  // 2. the phone's own Location switch (a granted permission does nothing while this is off)
  let on = await Location.hasServicesEnabledAsync().catch(() => true);
  if (!on) {
    await Location.enableNetworkProviderAsync().catch(() => undefined);   // Android's "turn on location" dialog
    on = await Location.hasServicesEnabledAsync().catch(() => false);
  }
  if (!on) return { skipped: "services_off" };

  // 3. balanced fix
  const balanced = await withTimeout(Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }), BALANCED_MS);
  if (balanced) return { reading: toReading(balanced) };

  // 4. last known position
  const last = await withTimeout(Location.getLastKnownPositionAsync({ maxAge: LAST_KNOWN_MAX_AGE_MS }), 3_000);
  if (last) return { reading: toReading(last) };

  // 5. GPS
  const gps = await withTimeout(Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }), GPS_MS);
  if (gps) return { reading: toReading(gps) };

  return { skipped: "unavailable" };
}

/** What to tell the person, and whether Settings can fix it. */
export function describeFailure(f: LocationFailure): { title: string; text: string; settings: boolean } {
  switch (f) {
    case "denied":
      return { title: "Location permission is off", text: "Allow location for Veekay Partner so your check in can record where you are.", settings: false };
    case "blocked":
      return { title: "Location is blocked for this app", text: "Open Settings > Permissions > Location and choose \"Allow only while using the app\".", settings: true };
    case "services_off":
      return { title: "Phone location is switched off", text: "Turn on Location in your phone's quick settings (or Settings > Location), then try again.", settings: true };
    default:
      return { title: "Couldn't get your location", text: "Move near a window or outdoors for a few seconds and try again. Make sure Location is on and set to high accuracy.", settings: true };
  }
}
