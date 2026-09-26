'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { createContext, useContext, useEffect, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { ApiError, apiRequest, csrfHeaders } from '@/core/api';
import { modules } from '@/core/module-registry';
import { useTheme } from '@/core/query-provider';

type Session = { authenticated: true; csrfToken: string };
const SessionContext = createContext<Session | null>(null);

export function useWorkspaceSession() {
  const session = useContext(SessionContext);
  if (!session) throw new Error('Workspace session is unavailable');
  return session;
}

export function WorkspaceShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { theme, setTheme } = useTheme();
  const session = useQuery({ queryKey: ['session'], queryFn: () => apiRequest<Session>('/api/v1/auth/session') });
  useEffect(() => {
    const unauthorized = () => { queryClient.clear(); router.replace('/login'); };
    const refreshed = (event: Event) => {
      queryClient.setQueryData(['session'], (event as CustomEvent<Session>).detail);
    };
    window.addEventListener('bbd:unauthorized', unauthorized);
    window.addEventListener('bbd:session-refreshed', refreshed);
    return () => {
      window.removeEventListener('bbd:unauthorized', unauthorized);
      window.removeEventListener('bbd:session-refreshed', refreshed);
    };
  }, [queryClient, router]);
  useEffect(() => {
    if (session.error instanceof ApiError && session.error.status === 401) {
      queryClient.clear();
      router.replace('/login');
    }
  }, [queryClient, router, session.error]);

  const logout = useMutation({
    mutationFn: () => apiRequest<void>('/api/v1/auth/logout', { method: 'POST', headers: csrfHeaders(session.data?.csrfToken ?? '') }),
    onSuccess: () => { queryClient.clear(); router.replace('/login'); },
  });

  if (session.isPending) return <main className="shell"><div className="status-panel skeleton" aria-label="Loading workspace" /></main>;
  if (session.isError || !session.data) return <main className="page"><section className="status-panel"><h1>Workspace is unavailable</h1><p className="muted">Reload after checking the local API.</p></section></main>;

  return <SessionContext.Provider value={session.data}>
    <div className="shell"><header className="topbar"><Link href="/knowledge/documents" className="brand-name">BBD-OS</Link><div className="top-actions"><Button className="secondary" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>Use {theme === 'light' ? 'dark' : 'light'} theme</Button><Button className="secondary" onClick={() => logout.mutate()} disabled={logout.isPending}>Sign out</Button></div></header>
      <div className="workspace"><nav className="workspace-nav" aria-label="Workspace">{modules.filter((module) => module.enabled).map((module) => <Link key={module.id} href={module.href} aria-current={pathname === module.href || (module.href !== '/sources' && pathname.startsWith(`${module.href}/`)) ? 'page' : undefined}>{module.label}</Link>)}</nav><main className="workspace-main">{children}</main></div>
      {logout.error && <p className="error" role="alert">{logout.error instanceof ApiError ? logout.error.message : 'Sign out failed.'}</p>}
    </div>
  </SessionContext.Provider>;
}
