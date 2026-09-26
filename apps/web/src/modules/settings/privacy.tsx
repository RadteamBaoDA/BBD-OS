'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { ApiError, apiRequest, csrfHeaders } from '@/core/api';
import { useWorkspaceSession } from '@/core/app-shell/workspace-shell';

type Privacy = { allow_remote_reasoning: boolean; allow_remote_embeddings: boolean };

export function PrivacySettings() {
  const { csrfToken } = useWorkspaceSession();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ['settings-privacy'], queryFn: () => apiRequest<Privacy>('/api/v1/settings/privacy') });
  const [draft, setDraft] = useState<Privacy | null>(null);
  const save = useMutation({ mutationFn: (value: Privacy) => apiRequest<Privacy>('/api/v1/settings/privacy', { method: 'PATCH', headers: { ...csrfHeaders(csrfToken), 'Content-Type': 'application/json' }, body: JSON.stringify(value) }), onSuccess: (value) => { setDraft(value); queryClient.setQueryData(['settings-privacy'], value); } });
  if (query.isPending) return <section className="content-panel skeleton" aria-label="Loading privacy settings" />;
  if (query.isError) return <section className="content-panel"><h1>Privacy settings unavailable</h1><p className="error">{query.error instanceof ApiError ? query.error.message : 'Could not load privacy settings.'}</p><Button className="secondary" onClick={() => query.refetch()}>Retry</Button></section>;
  const value = draft ?? query.data;
  return <section className="content-panel"><span className="brand">Local first</span><h1>Privacy</h1><p className="muted">Remote processing is off by default. Reasoning and embeddings have separate permissions. Local-only requests remain blocked until a local transport is available.</p><form className="form" onSubmit={(event) => { event.preventDefault(); save.mutate(value); }}><label><input type="checkbox" checked={value.allow_remote_reasoning} onChange={(event) => setDraft({ ...value, allow_remote_reasoning: event.target.checked })} /> Allow remote providers to process source text for reasoning</label><label><input type="checkbox" checked={value.allow_remote_embeddings} onChange={(event) => setDraft({ ...value, allow_remote_embeddings: event.target.checked })} /> Allow remote providers to process source text for embeddings</label>{save.error && <p className="error" role="alert">{save.error instanceof ApiError ? save.error.message : 'Could not save privacy settings.'}</p>}<Button type="submit" disabled={save.isPending}>Save privacy settings</Button></form></section>;
}
