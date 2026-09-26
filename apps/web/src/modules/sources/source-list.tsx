'use client';

import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/core/api';
import { useWorkspaceSession } from '@/core/app-shell/workspace-shell';
import { archiveSource, listSources, sourceKeys } from './api';
import { SourceForm } from './source-form';

export function SourceList() {
  const { csrfToken } = useWorkspaceSession();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const sources = useInfiniteQuery({ queryKey: sourceKeys.list, initialPageParam: undefined as string | undefined, queryFn: ({ pageParam }) => listSources(pageParam), getNextPageParam: (last) => last.next_cursor ?? undefined });
  const archive = useMutation({ mutationFn: (id: string) => archiveSource(id, csrfToken), onSuccess: () => queryClient.invalidateQueries({ queryKey: sourceKeys.all }) });
  const items = sources.data?.pages.flatMap((page) => page.items) ?? [];
  return <section className="content-panel"><div className="section-heading"><div><span className="brand">Library</span><h1>Sources</h1><p className="muted">Create a manual source before adding documents.</p></div><Button onClick={() => setAdding(true)}>New source</Button></div>
    {adding && <section className="sub-panel"><h2>New manual source</h2><SourceForm onSaved={() => setAdding(false)} /></section>}
    {sources.isPending && <div className="skeleton" aria-label="Loading sources" />}
    {sources.isError && <p className="error" role="alert">Could not load sources. <Button className="secondary" onClick={() => sources.refetch()}>Retry</Button></p>}
    {sources.isSuccess && items.length === 0 && <p className="empty-state">No sources yet. Create a manual source to start your library.</p>}
    {items.length > 0 && <ul className="record-list">{items.map((source) => <li key={source.id} className="record-row"><div><strong>{source.name}</strong><p className="muted">{source.type} · {source.status}</p></div>{source.status !== 'archived' && <Button className="secondary" disabled={archive.isPending} onClick={() => { if (window.confirm(`Archive ${source.name}? Its documents will be kept.`)) archive.mutate(source.id); }}>Archive</Button>}</li>)}</ul>}
    {archive.error && <p className="error" role="alert">{archive.error instanceof ApiError ? archive.error.message : 'Could not archive source.'}</p>}
    {sources.hasNextPage && <Button className="secondary" disabled={sources.isFetchingNextPage} onClick={() => sources.fetchNextPage()}>Load more</Button>}
  </section>;
}
