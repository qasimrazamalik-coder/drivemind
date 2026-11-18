import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { ConnProvider } from "../lib/conn";
import { C } from "../lib/theme";
import { ToastProvider } from "../lib/toast";

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <ConnProvider>
        <ToastProvider>
          <StatusBar style="light" />
          <Stack
            screenOptions={{
              headerStyle: { backgroundColor: C.panel },
              headerTintColor: C.text,
              contentStyle: { backgroundColor: C.bg },
            }}
          >
            <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
            <Stack.Screen name="pair" options={{ title: "Pair with your PC" }} />
            <Stack.Screen name="plan/[id]" options={{ title: "Review changes" }} />
          </Stack>
        </ToastProvider>
      </ConnProvider>
    </SafeAreaProvider>
  );
}
