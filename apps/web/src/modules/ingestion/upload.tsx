'use client';

import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { ApiError, apiRequest, csrfHeaders } from '@/core/api';
import { useWorkspaceSession } from '@/core/app-shell/workspace-shell';
import { listSources, sourceKeys, getRun } from '@/modules/sources/api';

export function Upload() {
  const { csrfToken } = useWorkspaceSession();
  const [sourceId, setSourceId] = useState('');
  const [runId, setRunId] = useState('');
  const [error, setError] = useState('');
  const sources = useInfiniteQuery({ queryKey: sourceKeys.list, initialPageParam: undefined as string | undefined, queryFn: ({ pageParam }) => listSources(pageParam), getNextPageParam: (last) => last.next_cursor ?? undefined });
  const run = useQuery({ queryKey: ['ingestion-run', runId], queryFn: () => getRun(runId), enabled: !!runId, refetchInterval: (query) => ['succeeded', 'needs_ocr', 'failed'].includes(query.state.data?.status ?? '') ? false : 1500 });
  const available = sources.data?.pages.flatMap((page) => page.items).filter((source) => source.status === 'active' && (source.type === 'file' || source.type === 'manual')) ?? [];

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    const form = new FormData(event.currentTarget);
    form.set('source_id', sourceId);
    try {
      const receipt = await apiRequest<{ run_id: string }>('/api/v1/documents/upload', { method: 'POST', headers: csrfHeaders(csrfToken), body: form });
      setRunId(receipt.run_id);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Upload failed.');
    }
  }

  return <section className="sub-panel">
    <h2>Upload a document</h2>
    <form className="form" onSubmit={upload}>
      <div className="field"><Label htmlFor="upload-source">Source</Label><select id="upload-source" className="input" value={sourceId} onChange={(event) => setSourceId(event.target.value)} required><option value="">Choose an active source</option>{available.map((source) => <option value={source.id} key={source.id}>{source.name}</option>)}</select></div>
      <div className="field"><Label htmlFor="upload-file">File</Label><input id="upload-file" className="input" name="file" type="file" accept=".txt,.md,.json,.csv,.pdf,.docx" required /><span className="muted">Up to 25 MiB. Supported text formats: TXT, Markdown, JSON, CSV, PDF, DOCX.</span></div>
      {error && <p className="error" role="alert">{error}</p>}
      {sources.isSuccess && available.length === 0 && <p className="empty-state">Create an active manual or file source before uploading.</p>}
      <Button type="submit" disabled={!sourceId || available.length === 0}>Upload</Button>
    </form>
    {runId && run.data && <div aria-live="polite"><h3>Upload progress</h3><p>Received: yes</p><p>Parsed: {run.data.status === 'needs_ocr' ? 'no extractable text' : run.data.stages.find((stage) => stage.stage_key === 'parse_file')?.status ?? 'queued'}</p><p>Chunked: {run.data.stages.find((stage) => stage.stage_key === 'parse_file')?.result_count ?? (run.data.status === 'running' ? 'processing' : '0')}</p><p>Embedded: not configured · Indexed: not configured</p>{run.data.error_code && <p className="error">Processing error: {run.data.error_code}</p>}</div>}
    {run.isError && <p className="error" role="alert">Could not load upload progress.</p>}
  </section>;
}
