export interface DeviceLocation {
  latitude: number;
  longitude: number;
  /** metres */
  accuracy: number;
}

/**
 * The device's current position, or null if it isn't available (denied, no GPS, timed out,
 * insecure page). Never throws — callers treat a missing location as "not shared".
 */
export function getDeviceLocation(timeoutMs = 8000): Promise<DeviceLocation | null> {
  if (typeof navigator === "undefined" || !navigator.geolocation) return Promise.resolve(null);
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), timeoutMs + 1500); // belt and braces: some browsers never call back
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        clearTimeout(timer);
        resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: pos.coords.accuracy });
      },
      () => {
        clearTimeout(timer);
        resolve(null);
      },
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 0 },
    );
  });
}
