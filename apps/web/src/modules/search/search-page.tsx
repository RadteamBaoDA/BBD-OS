'use client';

import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ApiError } from '@/core/api';
import { listSources, sourceKeys } from '@/modules/sources/api';
import { getSearchIndexStatus, searchDocuments } from './api';
import { SearchResults } from './search-results';

export function SearchPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const applied = searchParams.toString();
  const params = new URLSearchParams(applied);
  const query = params.get('q')?.trim() ?? '';
  const sourceId = params.get('source') ?? '';
  const dateFrom = params.get('from') ?? '';
  const dateTo = params.get('to') ?? '';
  const contentType = params.get('type') ?? '';
  const mode = params.get('mode') === 'lexical' ? 'lexical' : 'hybrid';
  const [draft, setDraft] = useState({ query, sourceId, dateFrom, dateTo, contentType, mode });
  useEffect(() => { setDraft({ query, sourceId, dateFrom, dateTo, contentType, mode }); }, [query, sourceId, dateFrom, dateTo, contentType, mode]);

  const sources = useInfiniteQuery({ queryKey: sourceKeys.list, initialPageParam: undefined as string | undefined, queryFn: ({ pageParam }) => listSources(pageParam), getNextPageParam: (last) => last.next_cursor ?? undefined });
  const index = useQuery({ queryKey: ['search-index'], queryFn: getSearchIndexStatus, refetchInterval: 10000 });
  const filters = {
    source_ids: sourceId ? [sourceId] : [],
    date_from: dateFrom ? `${dateFrom}T00:00:00.000Z` : null,
    date_to: dateTo ? `${dateTo}T23:59:59.999Z` : null,
    content_types: contentType ? [contentType] : [],
  };
  const results = useInfiniteQuery({
    queryKey: ['search', query, sourceId, dateFrom, dateTo, contentType, mode],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => searchDocuments(query, filters, mode, pageParam),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: query.length > 0,
  });
  const items = results.data?.pages.flatMap((page) => page.items) ?? [];
  const warnings = [...new Set(results.data?.pages.flatMap((page) => page.warnings) ?? [])];
  const effectiveMode = results.data?.pages.at(-1)?.effective_mode;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = new URLSearchParams();
    if (draft.query.trim()) next.set('q', draft.query.trim());
    if (draft.sourceId) next.set('source', draft.sourceId);
    if (draft.dateFrom) next.set('from', draft.dateFrom);
    if (draft.dateTo) next.set('to', draft.dateTo);
    if (draft.contentType.trim()) next.set('type', draft.contentType.trim());
    if (draft.mode === 'lexical') next.set('mode', 'lexical');
    router.push(`/search${next.size ? `?${next}` : ''}`);
  }

  return <section className="content-panel"><span className="brand">Knowledge</span><h1>Search</h1><p className="muted">Find source backed documents and open their cited revisions.</p>
    <form className="form" onSubmit={submit}><div className="field"><Label htmlFor="search-query">Search terms</Label><Input id="search-query" data-search-query type="search" maxLength={1000} value={draft.query} onChange={(event) => setDraft({ ...draft, query: event.target.value })} /></div>
      <div className="search-filters"><div className="field"><Label htmlFor="search-source">Source</Label><select id="search-source" className="input" value={draft.sourceId} onChange={(event) => setDraft({ ...draft, sourceId: event.target.value })}><option value="">All sources</option>{sources.data?.pages.flatMap((page) => page.items).map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}</select>{sources.hasNextPage && <Button type="button" className="secondary" disabled={sources.isFetchingNextPage} onClick={() => sources.fetchNextPage()}>Load more sources</Button>}{sources.isError && <span className="error" role="alert">Sources unavailable. <Button type="button" className="secondary" onClick={() => sources.refetch()}>Retry</Button></span>}</div>
        <div className="field"><Label htmlFor="search-from">From date</Label><Input id="search-from" type="date" value={draft.dateFrom} onChange={(event) => setDraft({ ...draft, dateFrom: event.target.value })} /></div>
        <div className="field"><Label htmlFor="search-to">To date</Label><Input id="search-to" type="date" min={draft.dateFrom || undefined} value={draft.dateTo} onChange={(event) => setDraft({ ...draft, dateTo: event.target.value })} /></div>
        <div className="field"><Label htmlFor="search-type">Content type</Label><Input id="search-type" placeholder="Exact type, e.g. text/plain" value={draft.contentType} onChange={(event) => setDraft({ ...draft, contentType: event.target.value })} /></div>
        <div className="field"><Label htmlFor="search-mode">Search mode</Label><select id="search-mode" className="input" value={draft.mode} onChange={(event) => setDraft({ ...draft, mode: event.target.value as 'lexical' | 'hybrid' })}><option value="hybrid">Hybrid when available</option><option value="lexical">Lexical only</option></select></div></div>
      <Button type="submit" disabled={!!draft.dateFrom && !!draft.dateTo && draft.dateFrom > draft.dateTo}>Search</Button>
    </form>
    {index.data && <p className="muted" role="status">Semantic index: {index.data.status} · {index.data.indexed_items} indexed · {index.data.failed_items} failed</p>}
    {index.isError && <p className="error" role="alert">Could not load indexing progress. <Button className="secondary" onClick={() => index.refetch()}>Retry</Button></p>}
    {!query && <p className="empty-state">Enter search terms to find documents.</p>}
    {query && results.isPending && <div className="skeleton" aria-label="Searching documents" />}
    {query && results.isError && <p className="error" role="alert">{results.error instanceof ApiError ? results.error.message : 'Search failed.'} <Button className="secondary" onClick={() => results.refetch()}>Retry</Button></p>}
    {results.data && <><p className="muted" role="status">{items.length} results loaded · {effectiveMode === 'lexical' ? 'Lexical search' : 'Hybrid search'}</p>{warnings.map((warning) => <p className="error" role="alert" key={warning}>{warning}</p>)}{items.length ? <SearchResults items={items} /> : <p className="empty-state">No results match these terms and filters.</p>}{results.hasNextPage && <Button className="secondary" disabled={results.isFetchingNextPage} onClick={() => results.fetchNextPage()}>{results.isFetchingNextPage ? 'Loading…' : 'Load more results'}</Button>}{results.isFetchNextPageError && <p className="error" role="alert">Could not load more results. <Button className="secondary" onClick={() => results.fetchNextPage()}>Retry</Button></p>}</>}
  </section>;
}
