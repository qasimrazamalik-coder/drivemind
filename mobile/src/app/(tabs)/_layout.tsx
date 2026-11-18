import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import { Redirect, Tabs } from "expo-router";
import { useEffect } from "react";
import { AppState, ColorValue } from "react-native";

import { checkAlerts, setupNotifications } from "../../lib/alerts";
import { useConn } from "../../lib/conn";
import { C } from "../../lib/theme";

type IconName = React.ComponentProps<typeof MaterialIcons>["name"];
const icon = (name: IconName) => ({ color }: { color: ColorValue }) => <MaterialIcons name={name} size={24} color={typeof color === "string" ? color : undefined} />;

export default function TabLayout() {
  const { ready, conn, api } = useConn();

  // While the app is open, check the PC for new alerts every minute and show them as phone notifications.
  useEffect(() => {
    if (!api) return;
    let alive = true;
    setupNotifications().catch(() => {});
    const tick = () => {
      if (alive && AppState.currentState === "active") checkAlerts(api).catch(() => {});
    };
    tick();
    const t = setInterval(tick, 60_000);
    const sub = AppState.addEventListener("change", (st) => st === "active" && tick());
    return () => {
      alive = false;
      clearInterval(t);
      sub.remove();
    };
  }, [api]);

  if (!ready) return null;
  if (!conn) return <Redirect href="/pair" />;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: C.accent,
        tabBarInactiveTintColor: C.muted,
        tabBarStyle: { backgroundColor: C.panel, borderTopColor: C.line },
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Home", tabBarIcon: icon("donut-large") }} />
      <Tabs.Screen name="plans" options={{ title: "Review", tabBarIcon: icon("fact-check") }} />
      <Tabs.Screen name="cleaner" options={{ title: "Cleaner", tabBarIcon: icon("cleaning-services") }} />
      <Tabs.Screen name="settings" options={{ title: "Settings", tabBarIcon: icon("tune") }} />
    </Tabs>
  );
}
