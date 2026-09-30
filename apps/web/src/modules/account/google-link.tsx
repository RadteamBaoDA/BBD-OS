'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ApiError, apiRequest, csrfHeaders } from '@/core/api';
import { useWorkspaceSession } from '@/core/app-shell/workspace-shell';

type GoogleStatus = { configured: boolean; linked: boolean };

export function GoogleLink() {
  const { csrfToken } = useWorkspaceSession();
  const queryClient = useQueryClient();
  const [password, setPassword] = useState('');
  const [providerError, setProviderError] = useState(false);
  useEffect(() => setProviderError(new URLSearchParams(window.location.search).get('google') === 'error'), []);
  const status = useQuery({ queryKey: ['auth-google-status'], queryFn: () => apiRequest<GoogleStatus>('/api/v1/auth/google/status') });
  const link = useMutation({
    mutationFn: async () => {
      await apiRequest<void>('/api/v1/auth/reauthenticate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) },
        body: JSON.stringify({ password }),
      });
      return apiRequest<{ authorization_url: string }>('/api/v1/auth/google/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) },
        body: JSON.stringify({ purpose: 'link' }),
      });
    },
    onSuccess: ({ authorization_url }) => window.location.assign(authorization_url),
  });
  const unlink = useMutation({
    mutationFn: async () => {
      await apiRequest<void>('/api/v1/auth/reauthenticate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) },
        body: JSON.stringify({ password }),
      });
      return apiRequest<void>('/api/v1/auth/google/unlink', { method: 'POST', headers: csrfHeaders(csrfToken) });
    },
    onSuccess: () => {
      setPassword('');
      queryClient.invalidateQueries({ queryKey: ['auth-google-status'] });
    },
  });
  const error = link.error ?? unlink.error;

  return <section className="status-panel">
    <h1>Google sign-in</h1>
    {!status.data?.configured && <p className="muted">Google sign-in is not configured by the administrator.</p>}
    {status.data?.configured && <>
      <p className="muted">{status.data.linked ? 'A Google account is linked.' : 'No Google account is linked.'}</p>
      {providerError && <p className="error" role="alert">Google account linking could not be completed.</p>}
      <p className="muted">Sign-in requests only basic profile and email access. Gmail access is requested separately when a mail source is configured.</p>
      <div className="field"><Label htmlFor="google-password">Confirm your password to continue</Label><Input id="google-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></div>
      {status.data.linked
        ? <Button type="button" className="secondary" disabled={!password || unlink.isPending} onClick={() => unlink.mutate()}>{unlink.isPending ? 'Unlinking…' : 'Unlink Google'}</Button>
        : <Button type="button" disabled={!password || link.isPending} onClick={() => link.mutate()}>{link.isPending ? 'Opening Google…' : 'Link Google account'}</Button>}
      {error && <p className="error" role="alert">{error instanceof ApiError ? error.message : 'The Google account change could not be completed.'}</p>}
    </>}
    {status.error && <p className="error" role="alert">Google sign-in status is unavailable.</p>}
  </section>;
}
