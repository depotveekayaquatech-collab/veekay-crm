import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import { api } from "@/api/api";
import { staffApi } from "@/api/staff";

const TOKEN_KEY = "veekay.push";
const KIND_KEY = "veekay.push.kind";

export type PushAudience = "partner" | "staff";

Notifications.setNotificationHandler({
  handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: false, shouldSetBadge: false }),
});

/**
 * Registers this phone for push messages (Firebase Cloud Messaging). Asks for the notification permission once the
 * person is signed in (Android 13+ shows the system prompt). Never throws: a phone without Google services, a build
 * without Firebase configured, or a denied permission just means no push; the in-app Alerts tab still works.
 */
export async function registerPush(audience: PushAudience): Promise<void> {
  if (Platform.OS !== "android") return;
  try {
    await Notifications.setNotificationChannelAsync("default", {
      name: "Tickets and updates",
      importance: Notifications.AndroidImportance.DEFAULT,
    });
    let { status } = await Notifications.getPermissionsAsync();
    if (status !== "granted") status = (await Notifications.requestPermissionsAsync()).status;
    if (status !== "granted") return;
    const token = (await Notifications.getDevicePushTokenAsync()).data as string;
    if (!token) return;
    await (audience === "staff" ? staffApi.registerDevice(token) : api.registerDevice(token));
    await SecureStore.setItemAsync(TOKEN_KEY, token);
    await SecureStore.setItemAsync(KIND_KEY, audience);
  } catch {
    /* push is optional */
  }
}

/** On sign-out this phone stops receiving this person's messages. */
export async function unregisterPush(): Promise<void> {
  try {
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    const audience = await SecureStore.getItemAsync(KIND_KEY);
    if (token) {
      await (audience === "staff" ? staffApi.unregisterDevice(token) : api.unregisterDevice(token)).catch(() => undefined);
      await SecureStore.deleteItemAsync(TOKEN_KEY);
      await SecureStore.deleteItemAsync(KIND_KEY);
    }
  } catch {
    /* ignore */
  }
}
