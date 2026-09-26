'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import { ApiError, apiRequest, csrfHeaders } from '@/core/api';
import { useWorkspaceSession } from '@/core/app-shell/workspace-shell';
import { getRun, retryRun } from './api';

export function SyncHistory({ runId }: { runId: string }) {
  const { csrfToken } = useWorkspaceSession();
  const run = useQuery({
    queryKey: ['ingestion-run', runId],
    queryFn: () => getRun(runId),
    refetchInterval: (query) => ['succeeded', 'needs_ocr', 'failed'].includes(query.state.data?.status ?? '') ? false : 1500,
  });
  const retry = useMutation({
    mutationFn: () => retryRun(runId, csrfToken),
    onSuccess: (receipt) => { void apiRequest(`/api/v1/ingestion/runs/${receipt.run_id}`); void run.refetch(); },
  });
  if (run.isPending) return <p className="muted">Loading collection run…</p>;
  if (run.isError) return <p className="error" role="alert">Could not load run: {run.error instanceof ApiError ? run.error.message : 'request failed'}</p>;
  const stages = run.data.stages;
  return <div className="sub-panel" aria-live="polite">
    <h3>Collection and processing</h3>
    <p>Received: {run.data.status === 'queued' ? 'queued' : run.data.status === 'failed' ? 'failed' : 'yes'}</p>
    {stages.map((stage) => <p key={stage.stage_key}>{stage.stage_key === 'parse_file' ? 'Parsed and chunked' : stage.stage_key}: {stage.status}{stage.error_code ? ` · ${stage.error_code}` : ''}</p>)}
    <p>Embedded: not configured · Indexed: not configured</p>
    {run.data.status === 'failed' && <button className="button secondary" disabled={retry.isPending} onClick={() => retry.mutate()}>Retry</button>}
    {retry.error && <p className="error" role="alert">{retry.error instanceof ApiError ? retry.error.message : 'Could not retry this run.'}</p>}
  </div>;
}
