import { useState } from "react";
import { Alert, Platform, Pressable, Text, View } from "react-native";

import { baseName, Client, human, Plan } from "../lib/api";
import { C } from "../lib/theme";
import { Btn, Card, Pill, s } from "./ui";

const runnable = (st: string) => st === "pending" || st === "approved";

/** Longest folder path shared by all destinations, so rows can show short relative paths. */
function commonDir(paths: string[]): string {
  if (!paths.length) return "";
  const split = (p: string) => p.split(/[\\/]/).slice(0, -1);
  const parts = paths.map(split);
  let i = 0;
  while (parts.every((x) => x[i] !== undefined && x[i] === parts[0][i])) i++;
  return parts[0].slice(0, i).join("/");
}
const relTo = (p: string, base: string) => {
  const norm = p.replace(/\\/g, "/");
  return base && norm.startsWith(base) ? norm.slice(base.length).replace(/^\//, "") : norm;
};

function confirm(title: string, msg: string): Promise<boolean> {
  if (Platform.OS === "web") return Promise.resolve(true);
  return new Promise((res) =>
    Alert.alert(title, msg, [
      { text: "Cancel", style: "cancel", onPress: () => res(false) },
      { text: "Go ahead", onPress: () => res(true) },
    ]),
  );
}

/** Review a plan from the phone: tick changes, approve + apply, reject, or undo. */
export function PlanView({ plan, api, onChange, notify }: { plan: Plan; api: Client; onChange: (p: Plan) => void; notify: (t: string) => void }) {
  const [picked, setPicked] = useState<Set<string>>(
    () => new Set(plan.actions.filter((a) => runnable(a.status) && (a.decision === "yes" || a.status === "approved")).map((a) => a.id)),
  );
  const [busy, setBusy] = useState<string | null>(null);
  const open = plan.actions.filter((a) => runnable(a.status));
  const dstBase = commonDir(plan.actions.filter((a) => a.dst && !a.dst.includes("quarantine")).map((a) => (a.dst as string).replace(/\\/g, "/")));
  const toggle = (id: string) => setPicked((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const all = open.length > 0 && open.every((a) => picked.has(a.id));

  async function run(kind: "apply" | "reject" | "undo") {
    const ids = [...picked].filter((id) => open.some((a) => a.id === id));
    if (kind !== "undo" && !ids.length) return notify("Tick at least one change");
    if (kind === "undo" && !(await confirm("Undo this plan?", "Everything this plan moved goes back where it was."))) return;
    if (kind === "apply" && !(await confirm(`Apply ${ids.length} change${ids.length > 1 ? "s" : ""}?`, "Deletes go to DriveMind's quarantine first, so you can undo."))) return;
    setBusy(kind);
    try {
      if (kind === "undo") {
        const r = await api.undo(plan.id);
        const rn = r.result.renamed || [];
        notify(`Restored ${r.result.restored} items${rn.length ? ` · ${rn.length} got a new name (a newer file is in the old place)` : ""}`);
        onChange(r.plan);
      } else if (kind === "reject") {
        onChange(await api.decide(plan.id, [], ids));
        notify("Rejected — DriveMind will learn from this");
      } else {
        await api.decide(plan.id, ids);
        const r = await api.apply(plan.id, ids);
        notify(`${r.result.done} done${r.result.failed ? `, ${r.result.failed} failed` : ""}${r.result.freed_bytes ? `, freed ${human(r.result.freed_bytes)}` : ""}`);
        onChange(r.plan);
        setPicked(new Set());
      }
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const sm = plan.summary;
  return (
    <Card title={plan.title}>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
        <Pill label={`${sm.actions} changes`} />
        {sm.waiting ? <Pill label={`${sm.waiting} waiting`} tone="ask" /> : null}
        {sm.frees_bytes ? <Pill label={`frees ${human(sm.frees_bytes)}`} tone="yes" /> : null}
        <Pill label={plan.status} tone={plan.status === "applied" ? "good" : "muted"} />
      </View>
      {dstBase ? <Text style={[s.muted, { marginBottom: 6 }]}>Into {dstBase}</Text> : null}
      {plan.notes.map((n) => <Text key={n} style={[s.muted, { marginBottom: 6 }]}>{n}</Text>)}
      {open.length > 1 ? (
        <Pressable onPress={() => setPicked(all ? new Set() : new Set(open.map((a) => a.id)))} style={{ paddingVertical: 6 }}>
          <Text style={{ color: C.accent }}>{all ? "Untick all" : `Tick all ${open.length}`}</Text>
        </Pressable>
      ) : null}
      {plan.actions.length === 0 ? <Text style={s.muted}>Nothing to do — already tidy.</Text> : null}
      {plan.actions.map((a) => {
        const can = runnable(a.status);
        const on = picked.has(a.id);
        const tone = a.status === "done" ? "good" : a.status === "failed" ? "bad" : a.status === "pending" ? (a.decision === "yes" ? "yes" : "ask") : "muted";
        const label = a.status === "pending" ? (a.decision === "yes" ? "auto" : "ask") : a.status;
        return (
          <Pressable
            key={a.id}
            disabled={!can}
            onPress={() => toggle(a.id)}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: on, disabled: !can }}
            style={{ flexDirection: "row", gap: 10, paddingVertical: 10, borderTopWidth: 1, borderTopColor: C.line, opacity: a.status === "skipped" || a.status === "rejected" ? 0.5 : 1 }}
          >
            <View style={{ width: 22, height: 22, borderRadius: 6, borderWidth: 1.5, borderColor: can ? (on ? C.accent : C.muted) : C.line, backgroundColor: on ? C.accent : "transparent", alignItems: "center", justifyContent: "center", marginTop: 2 }}>
              {on ? <Text style={{ color: C.accentInk, fontWeight: "800", fontSize: 13 }}>✓</Text> : null}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[s.text, { fontWeight: "600" }]} numberOfLines={2}>{baseName(a.src)}</Text>
              {a.dst && !a.dst.includes("quarantine") ? <Text style={{ color: C.accent, fontSize: 13 }} numberOfLines={2}>→ {relTo(a.dst, dstBase)}</Text> : null}
              <Text style={s.muted} numberOfLines={3}>{a.reason}</Text>
              {a.error ? <Text style={{ color: C.bad, fontSize: 13 }}>{a.error}</Text> : null}
            </View>
            <View style={{ alignItems: "flex-end", gap: 4 }}>
              <Pill label={label} tone={tone} />
              <Text style={[s.muted, { fontSize: 12, color: a.confidence < 0.8 ? C.warn : C.muted }]}>{Math.round(a.confidence * 100)}%</Text>
              <Text style={[s.muted, { fontSize: 12 }]}>{human(a.size)}</Text>
            </View>
          </Pressable>
        );
      })}
      <View style={{ gap: 8, marginTop: 12 }}>
        {open.length ? <Btn label={`Apply ${[...picked].length || ""} ticked`.replace("  ", " ")} busy={busy === "apply"} onPress={() => run("apply")} /> : null}
        {open.length ? <Btn label="Reject ticked" kind="ghost" busy={busy === "reject"} onPress={() => run("reject")} /> : null}
        {plan.status === "applied" ? <Btn label="Undo this plan" kind="danger" busy={busy === "undo"} onPress={() => run("undo")} /> : null}
      </View>
    </Card>
  );
}
