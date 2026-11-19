import AsyncStorage from "@react-native-async-storage/async-storage";

export type Conn = { host: string; port: number; token: string; id?: string; pc?: string };
export type Decision = "yes" | "ask" | "no";

export type Drive = {
  drive: string; total: number; used: number; free: number; free_percent: number;
  score: number; status: "good" | "watch" | "critical"; days_to_full: number | null; trend: string;
};
export type Hello = { pc: string; version: string; drive: Drive | null; drives: Drive[]; mode: string;
  unread_notices: number; waiting_plans: number };
export type Action = {
  id: string; op: string; src: string; dst: string | null; size: number; category: string; reason: string;
  confidence: number; option: string; decision: Decision; status: string; error: string | null;
};
export type Summary = { actions: number; bytes: number; frees_bytes: number; auto: number; waiting: number };
export type Plan = { id: string; title: string; kind: string; status: string; created: number;
  actions: Action[]; notes: string[]; summary: Summary };
export type PlanRow = { id: string; ts: number; title: string; status: string; kind: string; summary: Summary };
export type Notice = { id: number; ts: number; level: string; title: string; body: string | null; read: number };
export type CacheRow = { id: string; name: string; effect: string; size: number; paths: string[];
  command: string | null; choice: Decision; display_only: boolean; admin: boolean; apps_open: string[] };
export type Hit = { path: string; name: string; size: number; mtime: number; snippet: string };
export type Disk = { name: string; media: string; bus: string; size_gb: number | null; status: "good" | "watch" | "critical"; notes: string[] };
export type Tip = { id: string; title: string; detail: string; frees: number; action: string };
export type LiveEvent = { seq: number; ts: number; kind: string; source?: string };
export type Events = { boot: string; seq: number; events: LiveEvent[]; reset: boolean };
export type ChatSource = { path: string; name: string; snippet: string };
export type ChatAction = { label: string; kind: string; target: string };
export type ChatAnswer = { answer: string; sources: ChatSource[]; actions: ChatAction[]; intent: string; ai: boolean };
export type FoundPC = { host: string; port: number; pc: string; version: string; pairing_open: boolean };
export type Weekly = { days: number; freed_bytes: number; moved_files: number; cleaned_files: number;
  growth_bytes: number | null; plans_applied: number; top_categories: { name: string; files: number }[] };

const KEY = "drivemind.conn";

export async function loadConn(): Promise<Conn | null> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Conn) : null;
  } catch {
    return null;
  }
}

export async function saveConn(c: Conn | null): Promise<void> {
  if (c) await AsyncStorage.setItem(KEY, JSON.stringify(c));
  else await AsyncStorage.removeItem(KEY);
}

/** Accepts the QR link (drivemind://pair?host=..&port=..&token=..) or the typed code (host:port#token). */
export function parsePairing(text: string): Conn | null {
  const t = text.trim();
  if (t.startsWith("drivemind://")) {
    const q = t.split("?")[1] ?? "";
    const params: Record<string, string> = {};
    for (const part of q.split("&")) {
      const [k, v] = part.split("=");
      if (k) params[k] = decodeURIComponent(v ?? "");
    }
    const port = Number(params.port || 7878);
    if (!params.host || !params.token || !Number.isFinite(port)) return null;
    return { host: params.host, port, token: params.token, id: params.id };
  }
  const m = /^([\w.\-]+):(\d{2,5})#([\w\-]{16,})$/.exec(t);
  return m ? { host: m[1], port: Number(m[2]), token: m[3] } : null;
}

/** Short, timed fetch for finding PCs: most addresses on the Wi-Fi never answer. */
async function probe(url: string, ms: number, init?: RequestInit): Promise<Response | null> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } catch {
    return null;
  } finally {
    clearTimeout(t);
  }
}

/**
 * Find DriveMind PCs on this Wi-Fi: ask every address in the phone's /24 network for
 * /m/discover (open, returns only a PC name). 32 at a time, ~1.2 s each: a few seconds total.
 */
export async function discoverPCs(myIp: string, port = 7878, onFound?: (pc: FoundPC) => void): Promise<FoundPC[]> {
  const m = /^(\d+)\.(\d+)\.(\d+)\.(\d+)$/.exec(myIp);
  if (!m || myIp === "0.0.0.0" || myIp.startsWith("127.")) return [];
  const prefix = `${m[1]}.${m[2]}.${m[3]}.`;
  const hosts = Array.from({ length: 254 }, (_, i) => prefix + (i + 1)).filter((h) => h !== myIp);
  const found: FoundPC[] = [];
  let next = 0;
  async function worker() {
    while (next < hosts.length) {
      const host = hosts[next++];
      const r = await probe(`http://${host}:${port}/m/discover`, 1200);
      if (!r?.ok) continue;
      const d = (await r.json().catch(() => null)) as Omit<FoundPC, "host"> & { app?: string } | null;
      if (d?.app === "drivemind") {
        const pc = { host, port: d.port || port, pc: d.pc, version: d.version, pairing_open: d.pairing_open };
        found.push(pc);
        onFound?.(pc);
      }
    }
  }
  await Promise.all(Array.from({ length: 32 }, worker));
  return found;
}

/** Swap the 6-digit code shown on the PC for this phone's own token. */
export async function claimPin(host: string, port: number, pin: string, name: string): Promise<Conn> {
  const r = await probe(`http://${host}:${port}/m/claim`, 8000, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pin, name }),
  });
  if (!r) throw new ApiError(`Can't reach the PC at ${host}.`, 0);
  const d = (await r.json().catch(() => ({}))) as { token?: string; id?: string; pc?: string; detail?: string };
  if (!r.ok || !d.token) throw new ApiError(d.detail || "That code didn't work.", r.status);
  return { host, port, token: d.token, id: d.id, pc: d.pc };
}

// ---- offline cache: each screen keeps its last good answer, shown when the PC is away ----
const CACHE = "drivemind.cache.";
export async function cacheGet<T>(key: string): Promise<{ at: number; data: T } | null> {
  try {
    const raw = await AsyncStorage.getItem(CACHE + key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
export async function cachePut(key: string, data: unknown): Promise<void> {
  try {
    await AsyncStorage.setItem(CACHE + key, JSON.stringify({ at: Date.now(), data }));
  } catch {
    // storage full or unavailable: the app still works, just without the offline copy
  }
}

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export function client(conn: Conn) {
  const base = `http://${conn.host}:${conn.port}/m`;
  async function call<T>(path: string, method = "GET", body?: unknown, ms = 20000): Promise<T> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ms);
    try {
      const r = await fetch(base + path, {
        method,
        signal: ctrl.signal,
        headers: { Authorization: `Bearer ${conn.token}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new ApiError((data as { detail?: string }).detail || `Request failed (${r.status})`, r.status);
      return data as T;
    } catch (e) {
      if (e instanceof ApiError) throw e;
      throw new ApiError(`Can't reach your PC at ${conn.host}. Is DriveMind running and are you on the same Wi-Fi?`, 0);
    } finally {
      clearTimeout(timer);
    }
  }
  return {
    hello: () => call<Hello>("/hello"),
    advice: () => call<{ tips: Tip[]; total_possible: number }>("/advice"),
    notices: () => call<Notice[]>("/notices"),
    readNotices: () => call("/notices/read", "POST"),
    plans: () => call<PlanRow[]>("/plans"),
    pending: () => call<PlanRow[]>("/plans/pending"),
    plan: (id: string) => call<Plan>(`/plans/${id}`),
    decide: (id: string, approve: string[], reject: string[] = []) => call<Plan>(`/plans/${id}/decide`, "POST", { approve, reject }),
    apply: (id: string, ids?: string[]) =>
      call<{ result: { done: number; failed: number; freed_bytes: number }; plan: Plan }>(`/plans/${id}/apply`, "POST", { ids: ids ?? null }),
    undo: (id: string) =>
      call<{ result: { restored: number; renamed?: { was: string; now: string }[] }; plan: Plan }>(`/plans/${id}/undo`, "POST"),
    newClean: () => call<Plan>("/plans/clean", "POST", {}),
    newTemp: () => call<Plan>("/plans/temp", "POST", { roots: [] }),
    tidy: () => call<{ done: number; failed: number; freed_bytes: number; waiting: number }>("/tidy", "POST"),
    caches: () => call<CacheRow[]>("/caches"),
    search: (q: string) => call<Hit[]>(`/search?q=${encodeURIComponent(q)}`),
    ssd: () => call<Disk[]>("/ssd"),
    newArchive: () => call<Plan>("/plans/archive", "POST", { roots: [] }),
    settings: () => call<{ settings: { mode: string; options: Record<string, Decision> }; options: Record<string, string> }>("/settings"),
    setMode: (mode: string) => call("/settings/mode", "PUT", { mode }),
    setOption: (key: string, value: Decision) => call<{ mode: string }>("/settings/option", "PUT", { key, value }),
    setCache: (key: string, value: Decision) => call("/settings/cache", "PUT", { key, value }),
    events: (since: number, boot: string | null) =>
      call<Events>(`/events?since=${since}&timeout=25${boot ? `&boot=${boot}` : ""}`, "GET", undefined, 32000),
    chat: (question: string, history: { role: string; content: string }[]) =>
      call<ChatAnswer>("/chat", "POST", { question, history }, 120000),
    weekly: () => call<Weekly>("/report/weekly"),
    scanLatest: () => call<{ root?: string; categories?: { name: string; size: number }[] }>("/scan/latest"),
  };
}
export type Client = ReturnType<typeof client>;

export function human(n: number | null | undefined): string {
  if (n == null) return "–";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (Math.abs(v) >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return i === 0 ? `${v} B` : `${v.toFixed(1)} ${u[i]}`;
}

export function ago(ts: number): string {
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export const baseName = (p: string) => p.split(/[\\/]/).pop() || p;
