import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { AppState } from "react-native";

import { cacheGet, cachePut, client, Client, Conn, loadConn, saveConn } from "./api";

/** How many times each kind of change has happened since the app opened (see useLoad's `live`). */
export type LiveTicks = Record<string, number>;

type Ctx = {
  ready: boolean;
  conn: Conn | null;
  api: Client | null;
  online: boolean;
  ticks: LiveTicks;
  connect: (c: Conn) => Promise<void>;
  forget: () => Promise<void>;
};

const ConnContext = createContext<Ctx>({
  ready: false, conn: null, api: null, online: true, ticks: {}, connect: async () => {}, forget: async () => {},
});

/**
 * Live sync: long-polls the PC's /m/events while the app is open. The PC answers the moment
 * something changes there (a plan, an alert, a setting), and the screens showing that data
 * reload. Paused in the background, where the background task checks for alerts instead.
 */
function useLive(api: Client | null) {
  const [ticks, setTicks] = useState<LiveTicks>({});
  const [online, setOnline] = useState(true);
  const [active, setActive] = useState(AppState.currentState === "active");

  useEffect(() => {
    const sub = AppState.addEventListener("change", (st) => setActive(st === "active"));
    return () => sub.remove();
  }, []);

  useEffect(() => {
    if (!api || !active) return;
    let stop = false;
    let seq = 0;
    let boot: string | null = null;
    (async () => {
      while (!stop) {
        try {
          const r = await api.events(seq, boot);
          if (stop) return;
          setOnline(true);
          const first = boot === null;
          seq = r.seq;
          boot = r.boot;
          const kinds = new Set(r.events.map((e) => e.kind));
          if (r.reset) ["status", "plans", "notices", "settings"].forEach((k) => kinds.add(k));
          if (first) kinds.add("status"); // reconnected: refresh what is on screen
          if (kinds.size)
            setTicks((t) => {
              const n = { ...t };
              kinds.forEach((k) => (n[k] = (n[k] || 0) + 1));
              return n;
            });
        } catch {
          if (stop) return;
          setOnline(false);
          boot = null; // the PC may have restarted: start over when it is back
          await new Promise((res) => setTimeout(res, 5000));
        }
      }
    })();
    return () => {
      stop = true;
    };
  }, [api, active]);

  return { ticks, online };
}

export function ConnProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [conn, setConn] = useState<Conn | null>(null);

  useEffect(() => {
    loadConn().then((c) => {
      setConn(c);
      setReady(true);
    });
  }, []);

  const connect = useCallback(async (c: Conn) => {
    await saveConn(c);
    setConn(c);
  }, []);

  const forget = useCallback(async () => {
    await saveConn(null);
    setConn(null);
  }, []);

  const api = useMemo(() => (conn ? client(conn) : null), [conn]);
  const { ticks, online } = useLive(api);
  return (
    <ConnContext.Provider value={{ ready, conn, api, online, ticks, connect, forget }}>{children}</ConnContext.Provider>
  );
}

export const useConn = () => useContext(ConnContext);

type LoadOpts = {
  /** Reload when the PC reports one of these kinds of change. */
  live?: string[];
  /** Keep the last good answer on the phone and show it while the PC can't be reached. */
  cacheKey?: string;
};

/** Data hook: load on mount, on demand, and when the PC says it changed; falls back to the offline copy. */
export function useLoad<T>(fn: (() => Promise<T>) | null, deps: unknown[] = [], opts: LoadOpts = {}) {
  const { ticks } = useConn();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [staleSince, setStaleSince] = useState<number | null>(null);
  const hasData = useRef(false);

  const reload = useCallback(async () => {
    if (!fn) return;
    setLoading(true);
    try {
      const d = await fn();
      setData(d);
      hasData.current = true;
      setError(null);
      setStaleSince(null);
      if (opts.cacheKey) cachePut(opts.cacheKey, d);
    } catch (e) {
      setError((e as Error).message);
      if (opts.cacheKey && !hasData.current) {
        const c = await cacheGet<T>(opts.cacheKey);
        if (c) {
          setData(c.data);
          setStaleSince(c.at);
        }
      }
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    reload();
  }, [reload]);

  const liveKey = (opts.live || []).map((k) => ticks[k] || 0).join(",");
  const firstLive = useRef(true);
  useEffect(() => {
    if (firstLive.current) {
      firstLive.current = false;
      return;
    }
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveKey]);

  return { data, error, loading, reload, setData, staleSince };
}
