'use client';

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/core/api';
import { useWorkspaceSession } from '@/core/app-shell/workspace-shell';
import { archiveSource, getOperation, listSources, purgeSource, sourceKeys, triggerCollection, updateSourceStatus } from './api';
import { ConnectorSetup } from './connector-setup';
import { SourceForm } from './source-form';
import { SyncHistory } from './sync-history';

function PurgeProgress({ operationId }: { operationId: string }) {
  const operation = useQuery({ queryKey: ['operation', operationId], queryFn: () => getOperation(operationId), refetchInterval: (query) => ['succeeded', 'failed'].includes(query.state.data?.status ?? '') ? false : 1500 });
  if (operation.isPending) return <p className="muted">Checking deletion…</p>;
  if (operation.isError) return <p className="error" role="alert">Could not check deletion status.</p>;
  return <p role="status">Deletion {operation.data.status}{operation.data.error_code ? ` · ${operation.data.error_code}` : ''}</p>;
}

export function SourceList() {
  const { csrfToken } = useWorkspaceSession();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [addingConnector, setAddingConnector] = useState(false);
  const [runs, setRuns] = useState<Record<string, string>>({});
  const [noChanges, setNoChanges] = useState<Record<string, boolean>>({});
  const [operations, setOperations] = useState<Record<string, string>>({});
  const sources = useInfiniteQuery({ queryKey: sourceKeys.list, initialPageParam: undefined as string | undefined, queryFn: ({ pageParam }) => listSources(pageParam), getNextPageParam: (last) => last.next_cursor ?? undefined });
  const refresh = () => queryClient.invalidateQueries({ queryKey: sourceKeys.all });
  const archive = useMutation({ mutationFn: (id: string) => archiveSource(id, csrfToken), onSuccess: refresh });
  const purge = useMutation({ mutationFn: (id: string) => purgeSource(id, csrfToken), onSuccess: (operation) => { setOperations((current) => ({ ...current, [operation.source_id]: operation.operation_id })); refresh(); } });
  const status = useMutation({ mutationFn: ({ id, next }: { id: string; next: 'active' | 'paused' }) => updateSourceStatus(id, next, csrfToken), onSuccess: refresh });
  const collect = useMutation({ mutationFn: (id: string) => triggerCollection(id, csrfToken), onSuccess: (result, id) => { if (result.run_id) { setRuns((current) => ({ ...current, [id]: result.run_id! })); setNoChanges((current) => ({ ...current, [id]: false })); } else { setNoChanges((current) => ({ ...current, [id]: true })); } } });
  const items = sources.data?.pages.flatMap((page) => page.items) ?? [];

  return <section className="content-panel">
    <div className="section-heading"><div><span className="brand">Library</span><h1>Sources</h1><p className="muted">Connectors keep provider credentials in n8n. Source data remains local.</p></div>
      <div className="form-actions"><Button onClick={() => { setAdding(false); setAddingConnector((value) => !value); }}>Set up connector</Button><Button className="secondary" onClick={() => { setAddingConnector(false); setAdding((value) => !value); }}>New manual source</Button></div>
    </div>
    {adding && <section className="sub-panel"><h2>New manual source</h2><SourceForm onSaved={() => { setAdding(false); refresh(); }} /></section>}
    {addingConnector && <ConnectorSetup onSaved={() => { setAddingConnector(false); refresh(); }} />}
    {sources.isPending && <div className="skeleton" aria-label="Loading sources" />}
    {sources.isError && <p className="error" role="alert">Could not load sources. <Button className="secondary" onClick={() => sources.refetch()}>Retry</Button></p>}
    {sources.isSuccess && items.length === 0 && <p className="empty-state">No sources yet. Create a manual source or set up an RSS, web, or REST connector.</p>}
    {items.length > 0 && <ul className="record-list">{items.map((source) => <li key={source.id} className="record-row"><div className="record-content">
      <div><strong>{source.name}</strong><p className="muted">{source.type} · {source.status}{source.retired_at ? ` · retired ${new Date(source.retired_at).toLocaleString()}` : ''}</p>
        <p className="muted">Collected: {source.collected_at ? new Date(source.collected_at).toLocaleString() : 'never'} · Indexed: {source.indexed_at ? new Date(source.indexed_at).toLocaleString() : 'not configured'} · Collection error: {source.collection_error_code ?? 'none'} · Processing error: {source.processing_error_code ?? 'none'}</p></div>
      <div className="form-actions">
        {source.status !== 'archived' && source.status !== 'paused' && source.type !== 'manual' && <Button className="secondary" disabled={collect.isPending} onClick={() => collect.mutate(source.id)}>Sync now</Button>}
        {source.status !== 'archived' && <Button className="secondary" disabled={status.isPending} onClick={() => status.mutate({ id: source.id, next: source.status === 'paused' ? 'active' : 'paused' })}>{source.status === 'paused' ? 'Resume' : 'Pause'}</Button>}
        {source.status !== 'archived' && <Button className="secondary" disabled={archive.isPending} onClick={() => { if (window.confirm(`Archive ${source.name}? Its data will be kept.`)) archive.mutate(source.id); }}>Archive</Button>}
        <Button className="secondary" disabled={purge.isPending} onClick={() => { if (window.confirm(`Permanently delete ${source.name} and all of its documents and collected observations?`)) purge.mutate(source.id); }}>Delete all data</Button>
      </div>
      {runs[source.id] && <SyncHistory runId={runs[source.id]} />}
      {noChanges[source.id] && <p className="muted" role="status">Sync completed; no new records.</p>}
      {operations[source.id] && <PurgeProgress operationId={operations[source.id]} />}
    </div></li>)}</ul>}
    {(archive.error || purge.error || status.error || collect.error) && <p className="error" role="alert">{[archive.error, purge.error, status.error, collect.error].filter(Boolean).map((error) => error instanceof ApiError ? error.message : 'Source action failed.').join(' ')}</p>}
    {sources.hasNextPage && <Button className="secondary" disabled={sources.isFetchingNextPage} onClick={() => sources.fetchNextPage()}>Load more</Button>}
  </section>;
}
