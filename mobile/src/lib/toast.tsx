import { createContext, ReactNode, useCallback, useContext, useRef, useState } from "react";
import { Text, View } from "react-native";

import { C } from "./theme";

const ToastContext = createContext<(t: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [text, setText] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const show = useCallback((t: string) => {
    setText(t);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setText(null), 3500);
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      {text ? (
        <View pointerEvents="none" accessibilityLiveRegion="polite"
          style={{ position: "absolute", left: 16, right: 16, bottom: 90, backgroundColor: C.panel2, borderColor: C.line, borderWidth: 1, borderRadius: 12, padding: 14 }}>
          <Text style={{ color: C.text, fontSize: 14 }}>{text}</Text>
        </View>
      ) : null}
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
