import { router } from "expo-router";
import { Alert, Platform, Pressable, Text, View } from "react-native";

import { Btn, Card, ErrorBox, H1, Screen, Seg, s } from "../../components/ui";
import { Decision } from "../../lib/api";
import { useConn, useLoad } from "../../lib/conn";
import { C } from "../../lib/theme";
import { useToast } from "../../lib/toast";

const MODES = [
  { id: "safe", name: "Safe", desc: "Everything waits for your tap." },
  { id: "balanced", name: "Balanced", desc: "Safe jobs run by themselves; moving files asks first." },
  { id: "autopilot", name: "Autopilot", desc: "Runs everything except permanent changes." },
];

export default function Settings() {
  const { api, conn, forget } = useConn();
  const toast = useToast();
  const st = useLoad(api ? api.settings : null, [api]);
  const mode = st.data?.settings.mode;

  async function pickMode(id: string) {
    if (!api) return;
    try {
      await api.setMode(id);
      toast(`${id[0].toUpperCase() + id.slice(1)} mode on — your PC uses it now`);
      st.reload();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function setOpt(key: string, v: Decision) {
    if (!api || !st.data) return;
    try {
      const r = await api.setOption(key, v);
      st.setData({ ...st.data, settings: { ...st.data.settings, mode: r.mode, options: { ...st.data.settings.options, [key]: v } } });
    } catch (e) {
      toast((e as Error).message);
    }
  }

  function unpair() {
    const go = async () => {
      await forget();
      router.replace("/pair");
    };
    if (Platform.OS === "web") return go();
    Alert.alert("Disconnect this phone?", "To fully revoke it, also remove it on your PC under Settings > Phone.", [
      { text: "Cancel", style: "cancel" },
      { text: "Disconnect", style: "destructive", onPress: go },
    ]);
  }

  return (
    <Screen refreshing={st.loading} onRefresh={st.reload}>
      <H1 sub="Changes here apply on your PC straight away.">Settings</H1>
      {st.error ? <ErrorBox text={st.error} onRetry={st.reload} /> : null}

      <Card title="Mode">
        {MODES.map((m) => {
          const on = mode === m.id;
          return (
            <Pressable key={m.id} onPress={() => pickMode(m.id)} accessibilityRole="radio" accessibilityState={{ checked: on }}
              style={{ padding: 12, borderRadius: 12, borderWidth: 1, borderColor: on ? C.accent : C.line, marginBottom: 8, backgroundColor: on ? "rgba(94,234,212,0.06)" : "transparent" }}>
              <Text style={[s.text, { fontWeight: "700" }]}>{m.name}</Text>
              <Text style={s.muted}>{m.desc}</Text>
            </Pressable>
          );
        })}
        {mode === "custom" ? <Text style={s.muted}>Custom: you changed single switches below.</Text> : null}
      </Card>

      <Card title="Switches">
        {st.data
          ? Object.entries(st.data.options).map(([k, desc]) => (
              <View key={k} style={{ paddingVertical: 10, borderTopWidth: 1, borderTopColor: C.line, gap: 8 }}>
                <Text style={s.text}>{desc}</Text>
                <Seg value={st.data!.settings.options[k] ?? "ask"} onChange={(v) => setOpt(k, v)} />
              </View>
            ))
          : null}
      </Card>

      <Card title="This phone">
        <Text style={[s.muted, { marginBottom: 12 }]}>Connected to {conn?.pc || "your PC"} at {conn?.host}:{conn?.port}</Text>
        <Btn label="Disconnect" kind="danger" onPress={unpair} />
      </Card>
    </Screen>
  );
}
