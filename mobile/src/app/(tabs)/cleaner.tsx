import { router } from "expo-router";
import { useState } from "react";
import { Text, View } from "react-native";

import { Btn, Card, ErrorBox, H1, Screen, Seg, s } from "../../components/ui";
import { CacheRow, Decision, human } from "../../lib/api";
import { useConn, useLoad } from "../../lib/conn";
import { C } from "../../lib/theme";
import { useToast } from "../../lib/toast";

export default function Cleaner() {
  const { api } = useConn();
  const toast = useToast();
  const caches = useLoad(api ? api.caches : null, [api], { live: ["plans", "settings"], cacheKey: "caches" });
  const [busy, setBusy] = useState<"clean" | "temp" | "archive" | null>(null);

  async function setChoice(row: CacheRow, v: Decision) {
    if (!api) return;
    try {
      await api.setCache(row.id, v);
      caches.setData((caches.data ?? []).map((r) => (r.id === row.id ? { ...r, choice: v } : r)));
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function review(kind: "clean" | "temp" | "archive") {
    if (!api) return;
    setBusy(kind);
    try {
      const p = kind === "clean" ? await api.newClean() : kind === "temp" ? await api.newTemp() : await api.newArchive();
      router.push({ pathname: "/plan/[id]", params: { id: p.id } });
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const rows = [...(caches.data ?? [])].sort((a, b) => b.size - a.size);
  const found = rows.filter((r) => r.paths.length || r.command);
  const total = rows.filter((r) => !r.display_only).reduce((a, r) => a + r.size, 0);
  return (
    <Screen refreshing={caches.loading} onRefresh={caches.reload}>
      <H1 sub="Yes clears it automatically, Ask waits for you, No never touches it.">Cleaner</H1>
      {caches.error ? <ErrorBox text={caches.error} onRetry={caches.reload} /> : null}
      <Card>
        <Text style={[s.text, { marginBottom: 12 }]}>{caches.data ? `${human(total)} of caches on your PC` : "Measuring caches…"}</Text>
        <View style={{ gap: 8 }}>
          <Btn label="Review a cache clean" busy={busy === "clean"} onPress={() => review("clean")} />
          <Btn label="Find temporary junk" kind="ghost" busy={busy === "temp"} onPress={() => review("temp")} />
          <Btn label="Archive idle projects" kind="ghost" busy={busy === "archive"} onPress={() => review("archive")} />
        </View>
      </Card>
      <Card title="Caches">
        {found.map((r) => (
          <View key={r.id} style={{ paddingVertical: 10, borderTopWidth: 1, borderTopColor: C.line, gap: 8 }}>
            <View style={s.row}>
              <Text style={[s.text, { flex: 1, fontWeight: "600" }]}>{r.name}</Text>
              <Text style={s.muted}>{r.command && !r.size ? "–" : human(r.size)}</Text>
            </View>
            <Text style={s.muted}>{r.effect}{r.apps_open.length ? ` · ${r.apps_open.join(", ")} open` : ""}</Text>
            <Seg value={r.choice} disabled={r.display_only} onChange={(v) => setChoice(r, v)} />
          </View>
        ))}
        {rows.length > found.length ? <Text style={[s.muted, { marginTop: 8 }]}>{rows.length - found.length} other caches are not on this PC.</Text> : null}
      </Card>
    </Screen>
  );
}
