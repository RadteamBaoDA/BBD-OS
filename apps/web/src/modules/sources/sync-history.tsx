'use client';

import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import { useWorkspaceSession } from '@/core/app-shell/workspace-shell';
import { useDisplayPreferences } from '@/core/query-provider';
import { AppLocaleId, normalizeFormattingLocale } from '@/core/i18n';
import { connectorKeys, getSourceIngestion, retryRun, Source, sourceKeys } from './api';

function formatDate(value: string, locale: AppLocaleId, timezone: string): string {
  return new Intl.DateTimeFormat(normalizeFormattingLocale(locale), {
    dateStyle: 'medium', timeStyle: 'short', timeZone: timezone,
  }).format(new Date(value));
}

function statusKey(status: string): 'runQueued' | 'runRunning' | 'runSucceeded' | 'runNeedsOcr' | 'runFailed' {
  return status === 'running' ? 'runRunning' : status === 'succeeded' ? 'runSucceeded' : status === 'needs_ocr' ? 'runNeedsOcr' : status === 'failed' ? 'runFailed' : 'runQueued';
}

export function SyncHistory({ source }: { source: Source }) {
  const t = useTranslations('sources');
  const display = useDisplayPreferences();
  const { csrfToken } = useWorkspaceSession();
  const queryClient = useQueryClient();
  const history = useInfiniteQuery({
    queryKey: connectorKeys.ingestion(source.id),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => getSourceIngestion(source.id, pageParam),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    refetchInterval: (query) => query.state.data?.pages.some((page) => page.current_run) ? 1500 : false,
  });
  const retry = useMutation({
    mutationFn: (runId: string) => retryRun(runId, csrfToken),
    onSuccess: (receipt) => {
      void queryClient.invalidateQueries({ queryKey: ['ingestion-run', receipt.run_id] });
      void queryClient.invalidateQueries({ queryKey: connectorKeys.ingestion(source.id) });
      void queryClient.invalidateQueries({ queryKey: sourceKeys.detail(source.id) });
    },
  });
  if (history.isPending) return <p className="muted">{t('loading')}</p>;
  if (history.isError) return <p className="error" role="alert">{t('actionFailed')}</p>;
  const pages = history.data.pages;
  const current = pages[0]?.current_run ?? null;
  const runs = pages.flatMap((page) => page.items).filter((run) => run.run_id !== current?.run_id);
  const renderRun = (run: NonNullable<typeof current>, isCurrent: boolean) => <article className="source-run" key={run.run_id}>
    <div className="source-run-heading"><strong>{isCurrent ? t('currentRun') : formatDate(run.created_at, display.locale, display.timezone)}</strong><span>{t(statusKey(run.status))}</span></div>
    {run.error_code && <p className="error">{t('runError')}: {run.error_code}</p>}
    {run.stages.map((stage) => <p className="source-stage" key={stage.stage_key}>
      <span>{stage.stage_key}</span><span>{stage.status}{stage.error_code ? ` · ${stage.error_code}` : ''}</span>
      {stage.result_count !== null && <small>{t('resultCount')}: {stage.result_count}</small>}
    </p>)}
    {run.status === 'failed' && source.status === 'active' && <Button className="secondary" disabled={retry.isPending} onClick={() => retry.mutate(run.run_id)}>{t('retryRun')}</Button>}
  </article>;
  return <section className="source-history" aria-label={t('recentRuns')}>
    <h3>{t('recentRuns')}</h3>
    {current && renderRun(current, true)}
    {runs.map((run) => renderRun(run, false))}
    {!current && runs.length === 0 && <p className="muted">{t('noRuns')}</p>}
    <p className="muted">{t('embeddedStatus')}</p>
    {history.hasNextPage && <Button className="secondary" disabled={history.isFetchingNextPage} onClick={() => history.fetchNextPage()}>{t('loadMore')}</Button>}
    {(retry.error || history.isFetchNextPageError) && <p className="error" role="alert">{t('actionFailed')}</p>}
  </section>;
}
