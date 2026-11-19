import AsyncStorage from "@react-native-async-storage/async-storage";
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { useColorScheme, View } from "react-native";

import { applyScheme, Scheme, ThemePref } from "./theme";

const KEY = "drivemind.theme";

type Ctx = { pref: ThemePref; scheme: Scheme; setPref: (p: ThemePref) => void };
const AppearanceContext = createContext<Ctx>({ pref: "system", scheme: "dark", setPref: () => {} });

/**
 * System / Light / Dark. "System" follows the phone's own setting and changes with it.
 * The choice is saved on this phone. Switching remounts the app so every screen redraws
 * in the new colours (screens are cheap to rebuild; their data comes back from the cache).
 */
export function AppearanceProvider({ children }: { children: ReactNode }) {
  const system = useColorScheme();
  const [pref, setPrefState] = useState<ThemePref | null>(null);

  useEffect(() => {
    AsyncStorage.getItem(KEY)
      .then((v) => setPrefState(v === "light" || v === "dark" || v === "system" ? v : "system"))
      .catch(() => setPrefState("system"));
  }, []);

  const setPref = useCallback((p: ThemePref) => {
    setPrefState(p);
    AsyncStorage.setItem(KEY, p).catch(() => {});
  }, []);

  if (pref === null) return null; // a few milliseconds: avoids a flash of the wrong theme
  const scheme: Scheme = pref === "system" ? (system === "light" ? "light" : "dark") : pref;
  applyScheme(scheme); // before children render, so they read the right colours

  return (
    <AppearanceContext.Provider value={{ pref, scheme, setPref }}>
      <View key={scheme} style={{ flex: 1 }}>
        {children}
      </View>
    </AppearanceContext.Provider>
  );
}

export const useAppearance = () => useContext(AppearanceContext);
