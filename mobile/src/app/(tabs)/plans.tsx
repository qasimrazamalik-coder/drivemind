import { router } from "expo-router";
import { Pressable, Text, View } from "react-native";

import { Card, ErrorBox, H1, Pill, Screen, s } from "../../components/ui";
import { ago, human, PlanRow } from "../../lib/api";
import { useConn, useLoad } from "../../lib/conn";
import { C } from "../../lib/theme";

function Row({ p }: { p: PlanRow }) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={() => router.push({ pathname: "/plan/[id]", params: { id: p.id } })}
      style={({ pressed }) => [{ paddingVertical: 12, borderTopWidth: 1, borderTopColor: C.line }, pressed && { opacity: 0.6 }]}
    >
      <Text style={[s.text, { fontWeight: "600" }]} numberOfLines={2}>{p.title}</Text>
      <View style={{ flexDirection: "row", gap: 6, marginTop: 6, flexWrap: "wrap", alignItems: "center" }}>
        {p.summary.waiting ? <Pill label={`${p.summary.waiting} waiting`} tone="ask" /> : null}
        <Pill label={p.status} tone={p.status === "applied" ? "good" : "muted"} />
        <Text style={s.muted}>{p.summary.actions} changes{p.summary.frees_bytes ? ` · frees ${human(p.summary.frees_bytes)}` : ""} · {ago(p.ts)}</Text>
      </View>
    </Pressable>
  );
}

export default function Plans() {
  const { api } = useConn();
  const list = useLoad(api ? api.plans : null, [api]);
  const waiting = (list.data ?? []).filter((p) => p.summary.waiting && p.status === "proposed");
  const rest = (list.data ?? []).filter((p) => !waiting.includes(p));
  return (
    <Screen refreshing={list.loading} onRefresh={list.reload}>
      <H1 sub="Changes your PC proposed. Approve, reject or undo them from here.">Review</H1>
      {list.error ? <ErrorBox text={list.error} onRetry={list.reload} /> : null}
      <Card title="Waiting for you">
        {waiting.length ? waiting.map((p) => <Row key={p.id} p={p} />) : <Text style={s.muted}>Nothing is waiting.</Text>}
      </Card>
      <Card title="Recent">
        {rest.length ? rest.slice(0, 15).map((p) => <Row key={p.id} p={p} />) : <Text style={s.muted}>No plans yet.</Text>}
      </Card>
    </Screen>
  );
}
