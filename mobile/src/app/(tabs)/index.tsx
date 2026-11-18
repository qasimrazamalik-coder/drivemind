import { router } from "expo-router";
import { useState } from "react";
import { Text, View } from "react-native";

import { Btn, Card, ErrorBox, H1, Pill, Ring, Screen, s } from "../../components/ui";
import { ago, human } from "../../lib/api";
import { useConn, useLoad } from "../../lib/conn";
import { C } from "../../lib/theme";
import { useToast } from "../../lib/toast";

export default function Home() {
  const { api, conn } = useConn();
  const toast = useToast();
  const hello = useLoad(api ? api.hello : null, [api]);
  const tips = useLoad(api ? api.advice : null, [api]);
  const notices = useLoad(api ? api.notices : null, [api]);
  const disks = useLoad(api ? api.ssd : null, [api]);
  const [tidying, setTidying] = useState(false);
  const d = hello.data?.drive;

  const refresh = () => {
    hello.reload();
    tips.reload();
    notices.reload();
    disks.reload();
  };

  async function tidy() {
    if (!api) return;
    setTidying(true);
    try {
      const r = await api.tidy();
      toast(`Tidied: ${r.done} cleared${r.freed_bytes ? `, ${human(r.freed_bytes)} freed` : ""}${r.waiting ? ` · ${r.waiting} waiting for you` : ""}`);
      refresh();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setTidying(false);
    }
  }

  const msg = d ? { good: "Plenty of room.", watch: "Getting full — worth a clean.", critical: "Almost full — fix this now." }[d.status] : "";
  return (
    <Screen refreshing={hello.loading} onRefresh={refresh}>
      <H1 sub={hello.data ? `${hello.data.pc} · ${hello.data.mode} mode` : `Connecting to ${conn?.pc || conn?.host}…`}>DriveMind</H1>
      {hello.error ? <ErrorBox text={hello.error} onRetry={refresh} /> : null}

      {d ? (
        <Card>
          <View style={{ flexDirection: "row", gap: 18, alignItems: "center" }}>
            <Ring usedPercent={100 - d.free_percent} status={d.status} />
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={s.h2}>Health {d.score}/100</Text>
              <Pill label={d.status} tone={d.status === "good" ? "yes" : "ask"} />
              <Text style={[s.text, { marginTop: 6 }]}>{human(d.free)} free on {d.drive}</Text>
              <Text style={s.muted}>{d.days_to_full ? `Full in ~${Math.round(d.days_to_full)} days` : d.trend === "learning" ? "Learning how fast it fills" : "Not filling up"}</Text>
            </View>
          </View>
          <Text style={[s.muted, { marginTop: 12 }]}>{msg}</Text>
        </Card>
      ) : null}

      <Card title="Tidy now">
        <Text style={[s.muted, { marginBottom: 12 }]}>Runs only what your settings say Yes to: safe caches and temporary junk. Everything else waits for you.</Text>
        <Btn label="Tidy now" busy={tidying} onPress={tidy} />
        {hello.data?.waiting_plans ? (
          <View style={{ marginTop: 8 }}>
            <Btn label={`Review ${hello.data.waiting_plans} waiting plan${hello.data.waiting_plans > 1 ? "s" : ""}`} kind="ghost" onPress={() => router.push("/plans")} />
          </View>
        ) : null}
      </Card>

      <Card title="Top fixes">
        {tips.data?.tips.length ? (
          tips.data.tips.map((t) => (
            <View key={t.id} style={{ paddingVertical: 8, borderTopWidth: 1, borderTopColor: C.line }}>
              <Text style={[s.text, { fontWeight: "600" }]}>{t.title}</Text>
              <Text style={s.muted}>{t.detail}</Text>
            </View>
          ))
        ) : (
          <Text style={s.muted}>{tips.loading ? "Looking for the biggest wins…" : "No big wins right now."}</Text>
        )}
      </Card>

      <Card title="Alerts">
        {notices.data?.length ? (
          notices.data.slice(0, 6).map((n) => (
            <View key={n.id} style={{ paddingVertical: 8, borderTopWidth: 1, borderTopColor: C.line }}>
              <Text style={{ color: n.level === "critical" ? C.bad : n.level === "watch" ? C.warn : C.text, fontWeight: "600" }}>{n.title}</Text>
              <Text style={s.muted}>{n.body ? `${n.body} · ` : ""}{ago(n.ts)}</Text>
            </View>
          ))
        ) : (
          <Text style={s.muted}>No alerts.</Text>
        )}
      </Card>

      {disks.data?.length ? (
        <Card title="Disk health">
          {disks.data.map((x) => (
            <View key={x.name} style={{ paddingVertical: 8, borderTopWidth: 1, borderTopColor: C.line, gap: 4 }}>
              <View style={s.row}>
                <Text style={[s.text, { flex: 1, fontWeight: "600" }]}>{x.name}</Text>
                <Pill label={x.status} tone={x.status === "good" ? "yes" : x.status === "watch" ? "ask" : "bad"} />
              </View>
              <Text style={s.muted}>{x.notes.join(" · ")}</Text>
            </View>
          ))}
        </Card>
      ) : null}

      {hello.data?.drives && hello.data.drives.length > 1 ? (
        <Card title="All drives">
          {hello.data.drives.map((x) => (
            <View key={x.drive} style={[s.row, { paddingVertical: 6 }]}>
              <Text style={s.text}>{x.drive}</Text>
              <Text style={s.muted}>{human(x.free)} free · {x.score}/100</Text>
            </View>
          ))}
        </Card>
      ) : null}
    </Screen>
  );
}
