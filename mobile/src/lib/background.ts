import * as BackgroundTask from "expo-background-task";
import * as TaskManager from "expo-task-manager";
import { Platform } from "react-native";

import { checkAlerts } from "./alerts";
import { client, loadConn } from "./api";

/** Checks the PC for new alerts even when the app is closed (Android runs it about every 15+ minutes,
 * when the phone is on Wi-Fi and has battery). Works only while the phone is on the same Wi-Fi as the PC. */
export const ALERT_TASK = "drivemind-alert-check";

if (Platform.OS !== "web") {
  // must be defined at module scope, not inside a component
  TaskManager.defineTask(ALERT_TASK, async () => {
    try {
      const conn = await loadConn();
      if (conn) await checkAlerts(client(conn));
      return BackgroundTask.BackgroundTaskResult.Success;
    } catch {
      return BackgroundTask.BackgroundTaskResult.Failed;
    }
  });
}

export async function enableBackgroundAlerts(): Promise<boolean> {
  if (Platform.OS === "web") return false;
  const status = await BackgroundTask.getStatusAsync();
  if (status !== BackgroundTask.BackgroundTaskStatus.Available) return false;
  if (!(await TaskManager.isTaskRegisteredAsync(ALERT_TASK))) {
    await BackgroundTask.registerTaskAsync(ALERT_TASK, { minimumInterval: 15 });
  }
  return true;
}

export async function disableBackgroundAlerts(): Promise<void> {
  if (Platform.OS === "web") return;
  if (await TaskManager.isTaskRegisteredAsync(ALERT_TASK)) await BackgroundTask.unregisterTaskAsync(ALERT_TASK);
}
