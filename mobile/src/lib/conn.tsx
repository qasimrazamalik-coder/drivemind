import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { client, Client, Conn, loadConn, saveConn } from "./api";

type Ctx = {
  ready: boolean;
  conn: Conn | null;
  api: Client | null;
  connect: (c: Conn) => Promise<void>;
  forget: () => Promise<void>;
};

const ConnContext = createContext<Ctx>({ ready: false, conn: null, api: null, connect: async () => {}, forget: async () => {} });

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
  return <ConnContext.Provider value={{ ready, conn, api, connect, forget }}>{children}</ConnContext.Provider>;
}

export const useConn = () => useContext(ConnContext);

/** Small data hook: load on mount and on demand, with error text for the UI. */
export function useLoad<T>(fn: (() => Promise<T>) | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const reload = useCallback(async () => {
    if (!fn) return;
    setLoading(true);
    try {
      setData(await fn());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    reload();
  }, [reload]);
  return { data, error, loading, reload, setData };
}
