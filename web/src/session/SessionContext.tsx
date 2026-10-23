import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { fetchSession, isLoggedIn, type SessionInfo } from '../api/auth';

interface SessionState {
  session: SessionInfo | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<SessionInfo | null>;
  clear: () => void;
}

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (): Promise<SessionInfo | null> => {
    if (!isLoggedIn()) {
      setSession(null);
      setLoading(false);
      return null;
    }
    setLoading(true);
    try {
      const next = await fetchSession();
      setSession(next);
      setError(null);
      return next;
    } catch (reason) {
      setSession(null);
      setError(reason instanceof Error ? reason.message : '读取登录身份失败');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const clear = useCallback(() => {
    setSession(null);
    setError(null);
  }, []);

  const value = useMemo(() => ({ session, loading, error, refresh, clear }), [session, loading, error, refresh, clear]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const value = useContext(SessionContext);
  if (!value) throw new Error('useSession must be used within SessionProvider');
  return value;
}
