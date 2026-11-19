import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import type { Client } from "./api";

const SEEN = "drivemind.lastNotice";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true, // on Android, false would hide the drop-down alert
    shouldSetBadge: false,
  }),
});

export async function setupNotifications(): Promise<boolean> {
  if (Platform.OS === "web") return false;
  if (Platform.OS === "android") {
    // Android 13+ shows the permission prompt only after a channel exists
    await Notifications.setNotificationChannelAsync("drive", {
      name: "Drive alerts",
      importance: Notifications.AndroidImportance.HIGH,
      lightColor: "#e2b23f",
    });
  }
  const current = await Notifications.getPermissionsAsync();
  if (current.status === "granted") return true;
  const asked = await Notifications.requestPermissionsAsync();
  return asked.status === "granted";
}

/** Shows a phone notification for every PC alert that is newer than the last one we showed. */
export async function checkAlerts(api: Client): Promise<number> {
  if (Platform.OS === "web") return 0;
  const notices = await api.notices();
  const last = Number((await AsyncStorage.getItem(SEEN)) || 0);
  const fresh = notices.filter((n) => n.id > last && !n.read).sort((a, b) => a.id - b.id);
  for (const n of fresh.slice(-3)) {
    await Notifications.scheduleNotificationAsync({
      content: { title: n.title, body: n.body || "Open DriveMind for details." },
      trigger: null,
    });
  }
  const maxId = notices.reduce((m, n) => Math.max(m, n.id), last);
  await AsyncStorage.setItem(SEEN, String(maxId));
  return fresh.length;
}
