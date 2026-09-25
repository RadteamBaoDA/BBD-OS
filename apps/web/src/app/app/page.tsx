'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ApiError, apiRequest, csrfHeaders } from '@/core/api';
import { Button } from '@/components/ui/button';

type Session = { authenticated: true; csrfToken: string };
type SystemHealth = {
  overall: string;
  components: Record<string, { status: string; connectivity?: string }>;
};

const labels: Record<string, string> = {
  postgres: 'Database', redis: 'Background queue', worker: 'Worker', model_gateway: 'OmniRoute',
  graph: 'Knowledge graph', n8n: 'Connector workflows', browser: 'Browser collection',
};

export default function SystemPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const session = useQuery({ queryKey: ['session'], queryFn: () => apiRequest<Session>('/api/v1/auth/session') });
  const health = useQuery({ queryKey: ['system-health'], queryFn: () => apiRequest<SystemHealth>('/api/v1/system/health'), enabled: session.isSuccess });

  useEffect(() => {
    document.body.dataset.theme = theme;
  }, [theme]);
  useEffect(() => {
    if (session.isError && session.error instanceof ApiError && session.error.status === 401) {
      queryClient.clear();
      router.replace('/login');
    }
  }, [queryClient, router, session.error, session.isError]);

  const logout = useMutation({
    mutationFn: () => apiRequest<void>('/api/v1/auth/logout', { method: 'POST', headers: csrfHeaders(session.data?.csrfToken ?? '') }),
    onSuccess: () => { queryClient.clear(); router.replace('/login'); },
  });

  if (session.isPending || health.isPending) return <main className="shell"><div className="status-panel skeleton" aria-label="Loading system status" /></main>;
  if (health.isError) return <main className="page"><section className="status-panel"><h1>System status is unavailable</h1><p className="muted">Reload after checking the local API and database.</p></section></main>;

  return <main className="shell"><header className="topbar"><span className="brand-name">BBD-OS</span><div className="top-actions"><Button className="secondary" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>Use {theme === 'light' ? 'dark' : 'light'} theme</Button><Button className="secondary" onClick={() => logout.mutate()} disabled={logout.isPending}>Sign out</Button></div></header>
    <section className="status-panel"><span className="brand">Your local workspace</span><h1>System status</h1><p className="muted">Core services are checked live. Optional integrations will appear here when configured.</p>
      <div className="status-grid">{Object.entries(health.data.components).map(([key, component]) => <article className="status-item" key={key}><div className="status-label">{labels[key] ?? key}</div><div className="status-value">{key === 'model_gateway' && component.status === 'unconfigured' ? 'OmniRoute is not configured' : component.status.replaceAll('_', ' ')}{component.connectivity === 'not_tested' && component.status === 'configured' ? ' · connectivity not tested' : ''}</div></article>)}</div>
      <p className="muted" role="status">Overall: {health.data.overall}. No sources connected.</p>
      {logout.error && <p className="error" role="alert">{logout.error instanceof ApiError ? logout.error.message : 'Sign out failed.'}</p>}
    </section>
  </main>;
}
