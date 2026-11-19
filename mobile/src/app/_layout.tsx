import { Archivo_700Bold, Archivo_800ExtraBold, useFonts } from "@expo-google-fonts/archivo";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import "../lib/background"; // registers the background alert task at startup
import { AppearanceProvider, useAppearance } from "../lib/appearance";
import { ConnProvider } from "../lib/conn";
import { C } from "../lib/theme";
import { ToastProvider } from "../lib/toast";

export default function RootLayout() {
  const [loaded, error] = useFonts({ Archivo_700Bold, Archivo_800ExtraBold });
  if (!loaded && !error) return null; // brief; if the font fails, the phone's own font is used
  return (
    <SafeAreaProvider>
      <ConnProvider>
        <AppearanceProvider>
          <ToastProvider>
            <Themed />
          </ToastProvider>
        </AppearanceProvider>
      </ConnProvider>
    </SafeAreaProvider>
  );
}

function Themed() {
  const { scheme } = useAppearance();
  return (
    <>
      <StatusBar style={scheme === "light" ? "dark" : "light"} />
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
    </>
  );
}
