import { router } from "expo-router";
import { useState } from "react";
import { Text, View } from "react-native";

import { Btn, Card, ErrorBox, H1, Pill, Screen, Shelf, s } from "../../components/ui";
import { ago, human } from "../../lib/api";
import { useConn, useLoad } from "../../lib/conn";
import { C, F } from "../../lib/theme";
import { useToast } from "../../lib/toast";
import type { ShelfSeg } from "../../components/ui";

/** Same rule as the PC: a file type gets a block only if it is at least 0.5% of the drive. */
function shelfSegments(d: { drive: string; used: number; free: number },
  scan: { root?: string; categories?: { name: string; size: number }[] } | null): ShelfSeg[] {
  const cap = d.used + d.free;
  const same = !!scan?.root && scan.root.toLowerCase().startsWith(d.drive.toLowerCase());
  const types = same ? (scan?.categories || []).filter((c) => c.size >= cap * 0.005).slice(0, 6) : [];
  const segs: ShelfSeg[] = types.map((c, i) => ({ name: c.name, size: c.size, color: C.series[i % C.series.length] }));
  const typed = types.reduce((a, c) => a + c.size, 0);
  if (d.used - typed > 0) segs.push({ name: types.length ? "Other used" : "Used", size: d.used - typed, color: types.length ? C.used : C.manila });
  segs.push({ name: "Free", size: d.free, color: C.panel2 });
  return segs;
}

export default function Home() {
  const { api, conn, online } = useConn();
  const toast = useToast();
  const hello = useLoad(api ? api.hello : null, [api], { live: ["status", "plans", "settings", "notices"], cacheKey: "hello" });
  const tips = useLoad(api ? api.advice : null, [api], { live: ["status", "plans"], cacheKey: "advice" });
  const notices = useLoad(api ? api.notices : null, [api], { live: ["notices"], cacheKey: "notices" });
  const disks = useLoad(api ? api.ssd : null, [api], { cacheKey: "ssd" });
  const week = useLoad(api ? api.weekly : null, [api], { live: ["plans"], cacheKey: "weekly" });
  const scanned = useLoad(api ? api.scanLatest : null, [api], { live: ["scan"], cacheKey: "scan" });
  const [tidying, setTidying] = useState(false);
  const d = hello.data?.drive;

  const refresh = () => {
    hello.reload();
    tips.reload();
    notices.reload();
    disks.reload();
    week.reload();
    scanned.reload();
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
      {hello.staleSince ? (
        <Card>
          <Text style={s.text}>Offline · showing what your PC said {ago(hello.staleSince / 1000)}.</Text>
          <Text style={s.muted}>Changes need the PC. Pull down to try again.</Text>
        </Card>
      ) : hello.error ? <ErrorBox text={hello.error} onRetry={refresh} /> : null}
      {!online && !hello.error && hello.data ? <Text style={[s.muted, { marginBottom: 8 }]}>Reconnecting to your PC…</Text> : null}

      {d ? (
        <Card>
          {/* the drive as a shelf, same as the PC Overview: big free space, then used vs free */}
          <View style={{ flexDirection: "row", alignItems: "flex-start", gap: 10 }}>
            <Text style={{ backgroundColor: C.manila, color: C.manilaInk, fontFamily: F.display, fontSize: 13, paddingHorizontal: 6,
              paddingVertical: 2, borderRadius: 4, overflow: "hidden", marginTop: 8 }}>{d.drive}</Text>
            <View style={{ flex: 1 }}>
              <Text style={{ color: C.text, fontFamily: F.display, fontSize: 44, letterSpacing: -1, lineHeight: 50 }}>{human(d.free)}</Text>
              <Text style={s.muted}>free of {human(d.used + d.free)}</Text>
            </View>
          </View>
          <Shelf segments={shelfSegments(d, scanned.data)} capacity={d.used + d.free} status={d.status} />
          <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 12 }}>
            <View><Text style={s.muted}>Health</Text><Text style={[s.h2, { fontFamily: F.display }]}>{d.score}/100</Text></View>
            <View style={{ alignItems: "flex-end" }}><Text style={s.muted}>Full in</Text>
              <Text style={[s.h2, { fontFamily: F.display }]}>{!d.days_to_full ? (d.trend === "learning" ? "Learning" : "Not filling")
                : d.days_to_full > 365 ? "Over a year" : d.days_to_full > 60 ? `~${Math.round(d.days_to_full / 30)} months` : `~${Math.round(d.days_to_full)} days`}</Text></View>
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

      {week.data ? (
        <Card title="This week">
          <View style={[s.row, { justifyContent: "space-between" }]}>
            <View><Text style={s.h2}>{human(week.data.freed_bytes)}</Text><Text style={s.muted}>freed</Text></View>
            <View><Text style={s.h2}>{week.data.moved_files}</Text><Text style={s.muted}>files organized</Text></View>
            <View>
              <Text style={s.h2}>{week.data.growth_bytes == null ? "–" : `${week.data.growth_bytes >= 0 ? "+" : "−"}${human(Math.abs(week.data.growth_bytes))}`}</Text>
              <Text style={s.muted}>drive change</Text>
            </View>
          </View>
        </Card>
      ) : null}

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
