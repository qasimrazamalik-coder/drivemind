import { ReactNode } from "react";
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View, ViewStyle } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Svg, { Circle } from "react-native-svg";

import type { Decision } from "../lib/api";
import { C, statusColor } from "../lib/theme";

export function Screen({ children, refreshing, onRefresh }: { children: ReactNode; refreshing?: boolean; onRefresh?: () => void }) {
  return (
    <SafeAreaView style={s.screen} edges={["top", "left", "right"]}>
      <ScrollView
        contentContainerStyle={s.content}
        refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={C.accent} colors={[C.accent]} progressBackgroundColor={C.panel} /> : undefined}
      >
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

export function H1({ children, sub }: { children: ReactNode; sub?: string }) {
  return (
    <View style={{ marginBottom: 16 }}>
      <Text style={s.h1}>{children}</Text>
      {sub ? <Text style={s.muted}>{sub}</Text> : null}
    </View>
  );
}

export function Card({ title, right, children, style }: { title?: string; right?: ReactNode; children: ReactNode; style?: ViewStyle }) {
  return (
    <View style={[s.card, style]}>
      {title || right ? (
        <View style={s.cardHead}>
          {title ? <Text style={s.h2}>{title}</Text> : <View />}
          {right}
        </View>
      ) : null}
      {children}
    </View>
  );
}

export function Btn({ label, onPress, kind = "primary", busy, disabled, small }: {
  label: string; onPress: () => void; kind?: "primary" | "ghost" | "danger"; busy?: boolean; disabled?: boolean; small?: boolean;
}) {
  const st = kind === "primary" ? s.btn : kind === "danger" ? [s.btn, s.btnDanger] : [s.btn, s.btnGhost];
  const tx = kind === "primary" ? s.btnText : kind === "danger" ? [s.btnText, { color: C.bad }] : [s.btnText, { color: C.text, fontWeight: "500" as const }];
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={busy || disabled}
      style={({ pressed }) => [st, small && s.btnSmall, (pressed || busy || disabled) && { opacity: 0.6 }]}
    >
      {busy ? <ActivityIndicator color={kind === "primary" ? C.accentInk : C.text} /> : <Text style={[tx, small && { fontSize: 13 }]}>{label}</Text>}
    </Pressable>
  );
}

export function Seg({ value, onChange, disabled }: { value: Decision; onChange: (v: Decision) => void; disabled?: boolean }) {
  const opts: Decision[] = ["yes", "ask", "no"];
  return (
    <View style={[s.seg, disabled && { opacity: 0.5 }]}>
      {opts.map((o, i) => {
        const on = o === value;
        const bg = on ? (o === "yes" ? "rgba(94,234,212,0.18)" : o === "ask" ? "rgba(251,191,36,0.18)" : C.panel2) : "transparent";
        const fg = on ? (o === "yes" ? C.accent : o === "ask" ? C.warn : C.text) : C.muted;
        return (
          <Pressable
            key={o}
            disabled={disabled}
            accessibilityRole="button"
            accessibilityState={{ selected: on }}
            onPress={() => onChange(o)}
            style={[s.segBtn, { backgroundColor: bg }, i > 0 && { borderLeftWidth: 1, borderLeftColor: C.line }]}
          >
            <Text style={{ color: fg, fontSize: 13 }}>{o[0].toUpperCase() + o.slice(1)}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function Ring({ usedPercent, status, size = 132 }: { usedPercent: number; status?: string; size?: number }) {
  const stroke = 12;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const used = Math.max(0, Math.min(100, usedPercent));
  return (
    <View style={{ width: size, height: size, alignItems: "center", justifyContent: "center" }}>
      <Svg width={size} height={size} style={StyleSheet.absoluteFill}>
        <Circle cx={size / 2} cy={size / 2} r={r} stroke={C.line} strokeWidth={stroke} fill="none" />
        <Circle
          cx={size / 2} cy={size / 2} r={r} stroke={statusColor(status)} strokeWidth={stroke} fill="none"
          strokeLinecap="round" strokeDasharray={`${(c * used) / 100} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </Svg>
      <Text style={{ color: C.text, fontSize: 26, fontWeight: "700" }}>{Math.round(used)}%</Text>
      <Text style={s.muted}>used</Text>
    </View>
  );
}

export function Pill({ label, tone = "muted" }: { label: string; tone?: "muted" | "yes" | "ask" | "good" | "bad" }) {
  const color = { muted: C.muted, yes: C.accent, ask: C.warn, good: C.good, bad: C.bad }[tone];
  return (
    <View style={[s.pill, { borderColor: tone === "muted" ? C.line : color }]}>
      <Text style={{ color, fontSize: 12 }}>{label}</Text>
    </View>
  );
}

export function ErrorBox({ text, onRetry }: { text: string; onRetry?: () => void }) {
  return (
    <Card style={{ borderColor: C.bad }}>
      <Text style={{ color: C.text, marginBottom: onRetry ? 10 : 0 }}>{text}</Text>
      {onRetry ? <Btn label="Try again" kind="ghost" small onPress={onRetry} /> : null}
    </Card>
  );
}

export const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  content: { padding: 16, paddingBottom: 40 },
  h1: { color: C.text, fontSize: 26, fontWeight: "700", letterSpacing: -0.3 },
  h2: { color: C.text, fontSize: 16, fontWeight: "600" },
  muted: { color: C.muted, fontSize: 13, lineHeight: 19 },
  text: { color: C.text, fontSize: 15, lineHeight: 21 },
  mono: { color: C.text, fontSize: 12, fontFamily: "monospace" },
  card: { backgroundColor: C.panel, borderColor: C.line, borderWidth: 1, borderRadius: 14, padding: 16, marginBottom: 12 },
  cardHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 12, gap: 8 },
  btn: { backgroundColor: C.accent, borderRadius: 10, paddingVertical: 12, paddingHorizontal: 16, alignItems: "center", justifyContent: "center", minHeight: 46 },
  btnSmall: { paddingVertical: 7, paddingHorizontal: 12, minHeight: 34 },
  btnGhost: { backgroundColor: "transparent", borderWidth: 1, borderColor: C.line },
  btnDanger: { backgroundColor: "transparent", borderWidth: 1, borderColor: "rgba(248,113,113,0.5)" },
  btnText: { color: C.accentInk, fontSize: 15, fontWeight: "700" },
  seg: { flexDirection: "row", alignSelf: "flex-start", borderWidth: 1, borderColor: C.line, borderRadius: 9, overflow: "hidden" },
  segBtn: { paddingVertical: 7, paddingHorizontal: 12, minWidth: 46, alignItems: "center" },
  pill: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2, alignSelf: "flex-start" },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  divider: { height: 1, backgroundColor: C.line, marginVertical: 10 },
});
