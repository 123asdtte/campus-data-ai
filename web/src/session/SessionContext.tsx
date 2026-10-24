import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  fetchSession,
  isLoggedIn,
  notifySessionExpired,
  SessionExpiredError,
  SESSION_EXPIRED_EVENT,
  type SessionInfo,
} from '../api/auth';
import { invalidateDemoData } from '../demo/useDemoData';

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
      if (reason instanceof SessionExpiredError) {
        setError(reason.message);
        notifySessionExpired();
        return null;
      }
      setError(reason instanceof Error ? reason.message : '读取登录身份失败');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const onExpired = () => {
      invalidateDemoData();
      setSession(null);
      setError('登录状态已失效，请重新登录');
      setLoading(false);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

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
