'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { ApiError, apiRequest } from '@/core/api';
import { useDisplayPreferences } from '@/core/query-provider';

export type RealtimeStatus = 'connecting' | 'connected' | 'reconnecting' | 'unavailable' | 'expired';

type RealtimeContextValue = {
  status: RealtimeStatus;
  newDocumentCount: number;
  documentRefreshRequired: boolean;
  documentRefreshFailed: boolean;
  consumeDocumentUpdates: () => Promise<void>;
};

type ProtectedReadPath = '/api/v1/realtime/snapshot' | '/api/v1/auth/session';
type SnapshotAttempt = { id: number; controller: AbortController };
class SupersededSnapshotAttempt extends Error {}

async function protectedJsonRead<T>(
  path: ProtectedReadPath,
  signal: AbortSignal,
  isCurrent: () => boolean,
): Promise<T> {
  const response = await fetch(path, {
    cache: 'no-store', credentials: 'same-origin', signal,
  });
  if (!isCurrent()) throw new SupersededSnapshotAttempt();
  if (response.status === 401) throw new ApiError(401, 'Authentication required');
  let body: unknown;
  try {
    body = await response.json();
  } catch (error) {
    if (!response.ok) throw new ApiError(response.status, 'Request failed');
    throw error;
  }
  if (!isCurrent()) throw new SupersededSnapshotAttempt();
  if (!response.ok) {
    const message = body && typeof body === 'object'
      && 'error' in body && typeof body.error === 'object' && body.error
      && 'message' in body.error && typeof body.error.message === 'string'
      ? body.error.message : 'Request failed';
    throw new ApiError(response.status, message);
  }
  return body as T;
}

type Snapshot = { cursor: string; floor_sequence: string };
type ReplayEnvelope = { schema_version: 1 };
type SourceEvent = ReplayEnvelope & {
  source_id: string; generation: number; status: 'active' | 'paused' | 'archived';
  connector_state?: string | null; operation_id?: string | null;
};
type IngestionEvent = ReplayEnvelope & {
  source_id: string; run_id: string; status: 'queued' | 'running' | 'retrying' | 'succeeded' | 'failed' | 'cancelled' | 'needs_ocr';
  stage_key?: string | null; stage_status?: string | null;
};
type KnowledgeEvent = ReplayEnvelope & {
  scope?: 'source' | 'index'; source_id?: string | null; document_id?: string | null; version?: number | null;
  deleted: boolean; index_generation_id?: string | null;
  index_status?: 'queued' | 'running' | 'active' | 'failed' | 'retired' | null;
  indexed_items?: number | null; failed_items?: number | null;
};

const RealtimeContext = createContext<RealtimeContextValue | null>(null);
const CURSOR_RE = /^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}):(0|[1-9][0-9]{0,18})$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const MAX_QUEUED_DOCUMENTS = 500;

export function useRealtime() {
  const value = useContext(RealtimeContext);
  if (!value) throw new Error('Realtime status is unavailable');
  return value;
}

function parseEnvelope<T extends ReplayEnvelope>(data: string): T | null {
  try {
    const value: unknown = JSON.parse(data);
    if (!value || typeof value !== 'object' || (value as ReplayEnvelope).schema_version !== 1) return null;
    return value as T;
  } catch {
    return null;
  }
}

function validCursor(value: string): boolean {
  return value.length <= 60 && CURSOR_RE.test(value);
}

function isCurrent(cursor: string, previous: string): boolean {
  const nextMatch = CURSOR_RE.exec(cursor);
  const previousMatch = CURSOR_RE.exec(previous);
  if (!nextMatch || !previousMatch || nextMatch[1] !== previousMatch[1]) return false;
  return BigInt(nextMatch[2]) > BigInt(previousMatch[2]);
}

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const display = useDisplayPreferences();
  const t = useTranslations('shell');
  const session = useQuery({
    queryKey: ['session'],
    queryFn: () => apiRequest<{ authenticated: true; csrfToken: string }>('/api/v1/auth/session'),
  });
  const isAuthenticated = Boolean(session.data);
  const sessionExpired = !isAuthenticated && session.error instanceof ApiError && session.error.status === 401;
  const [status, setStatus] = useState<RealtimeStatus>('connecting');
  const [barrierGeneration, setBarrierGeneration] = useState<number | null>(null);
  const [newDocumentCount, setNewDocumentCount] = useState(0);
  const [documentRefreshRequired, setDocumentRefreshRequired] = useState(false);
  const [documentRefreshFailed, setDocumentRefreshFailed] = useState(false);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const queuedDocuments = useRef(new Map<string, number>());
  const documentRevision = useRef(0);
  const unknownChangeRevision = useRef(0);
  const fullRefreshQueued = useRef(false);
  const cursorRef = useRef('');

  const queueDocumentUpdate = useCallback((id: string | null) => {
    documentRevision.current += 1;
    if (!id || fullRefreshQueued.current || queuedDocuments.current.size >= MAX_QUEUED_DOCUMENTS) {
      queuedDocuments.current.clear();
      unknownChangeRevision.current = documentRevision.current;
      fullRefreshQueued.current = true;
    } else {
      queuedDocuments.current.set(id, documentRevision.current);
    }
    setNewDocumentCount(queuedDocuments.current.size);
    if (fullRefreshQueued.current) setDocumentRefreshRequired(true);
  }, []);

  const invalidateOperationalQueries = useCallback(async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ['sources'] }),
      client.invalidateQueries({ queryKey: ['source-ingestion'] }),
      client.invalidateQueries({ queryKey: ['ingestion-run'] }),
      client.invalidateQueries({ queryKey: ['connector-catalog'] }),
      client.invalidateQueries({ queryKey: ['connector-configuration'] }),
      client.invalidateQueries({ queryKey: ['connector-activation'] }),
      client.invalidateQueries({ queryKey: ['operation'] }),
      client.invalidateQueries({ queryKey: ['search-index'] }),
    ]);
  }, [client]);

  const consumeDocumentUpdates = useCallback(async () => {
    const generation = display.authGeneration;
    const consumed = new Map(queuedDocuments.current);
    const unknownRevision = unknownChangeRevision.current;
    try {
      await client.invalidateQueries(
        { queryKey: ['documents'], exact: true },
        { throwOnError: true },
      );
      if (!display.isCurrentGeneration(generation)) return;
      for (const [id, revision] of consumed) {
        if (queuedDocuments.current.get(id) === revision) queuedDocuments.current.delete(id);
      }
      setNewDocumentCount(queuedDocuments.current.size);
      if (unknownChangeRevision.current === unknownRevision) {
        fullRefreshQueued.current = false;
        setDocumentRefreshRequired(false);
      }
      setDocumentRefreshFailed(false);
    } catch {
      if (display.isCurrentGeneration(generation)) setDocumentRefreshFailed(true);
    }
  }, [client, display.authGeneration, display.isCurrentGeneration]);

  useEffect(() => {
    const generation = display.authGeneration;
    const sessionState = isAuthenticated
      ? 'authenticated'
      : sessionExpired ? 'expired' : 'unavailable';
    if (sessionState !== 'authenticated') {
      setBarrierGeneration(generation);
      setStatus(sessionState);
      return;
    }

    let active = true;
    let attemptSequence = 0;
    let currentAttempt: SnapshotAttempt | null = null;
    let eventSource: EventSource | null = null;
    let authCheckController: AbortController | null = null;
    let retryDelay = 1000;
    setBarrierGeneration(null);
    setStatus('connecting');
    const isCurrentGeneration = () => active && display.isCurrentGeneration(generation);
    const ownsAttempt = (attempt: SnapshotAttempt) =>
      isCurrentGeneration() && currentAttempt === attempt && !attempt.controller.signal.aborted;
    const supersedeAttempt = () => {
      currentAttempt?.controller.abort();
      authCheckController?.abort();
      authCheckController = null;
      const attempt = { id: ++attemptSequence, controller: new AbortController() };
      currentAttempt = attempt;
      return attempt;
    };
    const cancelAttempt = () => {
      currentAttempt?.controller.abort();
      currentAttempt = null;
      authCheckController?.abort();
      authCheckController = null;
    };
    const closeStream = () => {
      eventSource?.close();
      eventSource = null;
      authCheckController?.abort();
      authCheckController = null;
    };
    const clearSnapshotRetry = () => {
      if (retryRef.current) clearTimeout(retryRef.current);
      retryRef.current = null;
    };
    const openSnapshot = async (
      reconnect: boolean, attempt: SnapshotAttempt, possibleDocumentChanges: boolean,
    ) => {
      if (!ownsAttempt(attempt)) return;
      try {
        const snapshot = await protectedJsonRead<Snapshot>(
          '/api/v1/realtime/snapshot', attempt.controller.signal, () => ownsAttempt(attempt),
        );
        if (!ownsAttempt(attempt)) return;
        if (!validCursor(snapshot.cursor) || !/^(0|[1-9][0-9]{0,18})$/.test(snapshot.floor_sequence)) {
          setStatus('unavailable');
          scheduleSnapshotRetry();
          return;
        }
        if (reconnect) {
          await invalidateOperationalQueries();
          if (!ownsAttempt(attempt)) return;
          if (possibleDocumentChanges) queueDocumentUpdate(null);
        }
        if (!ownsAttempt(attempt)) return;
        openStream(snapshot.cursor, attempt);
        if (ownsAttempt(attempt)) setBarrierGeneration(generation);
      } catch (error) {
        if (!ownsAttempt(attempt) || error instanceof SupersededSnapshotAttempt) return;
        if (error instanceof ApiError && error.status === 401) {
          setStatus('expired');
          window.dispatchEvent(new Event('bbd:unauthorized'));
        } else {
          setStatus('unavailable');
          setBarrierGeneration(generation);
          scheduleSnapshotRetry();
        }
      }
    };
    const scheduleSnapshotRetry = () => {
      if (!isCurrentGeneration() || retryRef.current) return;
      retryRef.current = setTimeout(() => {
        retryRef.current = null;
        const attempt = supersedeAttempt();
        void openSnapshot(true, attempt, true);
      }, retryDelay);
      retryDelay = Math.min(30_000, retryDelay * 2);
    };
    const resync = (possibleDocumentChanges: boolean) => {
      const attempt = supersedeAttempt();
      closeStream();
      if (!ownsAttempt(attempt)) return;
      setStatus('reconnecting');
      void openSnapshot(true, attempt, possibleDocumentChanges);
    };
    const register = (
      stream: EventSource, attempt: SnapshotAttempt, name: string,
      callback: (event: MessageEvent<string>) => void,
    ) => {
      stream.addEventListener(name, (event) => {
        if (!(event instanceof MessageEvent) || eventSource !== stream || !ownsAttempt(attempt)) return;
        const id = event.lastEventId;
        if (!validCursor(id) || (cursorRef.current && !isCurrent(id, cursorRef.current))) {
          if (id && CURSOR_RE.exec(id)?.[1] !== CURSOR_RE.exec(cursorRef.current)?.[1]) resync(true);
          return;
        }
        callback(event as MessageEvent<string>);
        if (eventSource === stream && ownsAttempt(attempt)) cursorRef.current = id;
      });
    };
    const openStream = (cursor: string, attempt: SnapshotAttempt) => {
      if (!ownsAttempt(attempt) || !validCursor(cursor)) return;
      closeStream();
      if (!ownsAttempt(attempt)) return;
      cursorRef.current = cursor;
      const stream = new EventSource(`/api/v1/realtime/events?cursor=${encodeURIComponent(cursor)}`);
      eventSource = stream;
      const ownsStream = () => eventSource === stream && ownsAttempt(attempt);
      stream.onopen = () => {
        if (!ownsStream()) return;
        retryDelay = 1000;
        clearSnapshotRetry();
        setStatus('connected');
      };
      stream.onerror = () => {
        if (!ownsStream()) return;
        setStatus('reconnecting');
        authCheckController?.abort();
        const controller = new AbortController();
        authCheckController = controller;
        const ownsAuthCheck = () => ownsStream() && authCheckController === controller && !controller.signal.aborted;
        void protectedJsonRead<unknown>(
          '/api/v1/auth/session', controller.signal, ownsAuthCheck,
        ).catch((error) => {
          if (!ownsAuthCheck()) return;
          if (error instanceof ApiError && error.status === 401) {
            setStatus('expired');
            window.dispatchEvent(new Event('bbd:unauthorized'));
          }
        }).finally(() => {
          if (authCheckController === controller) authCheckController = null;
        });
      };
      register(stream, attempt, 'source.changed', (event) => {
        const value = parseEnvelope<SourceEvent>(event.data);
        if (!value || !UUID_RE.test(value.source_id) || !Number.isSafeInteger(value.generation)) { resync(true); return; }
        void Promise.all([
          client.invalidateQueries({ queryKey: ['sources'] }),
          client.invalidateQueries({ queryKey: ['connector-configuration', value.source_id] }),
          client.invalidateQueries({ queryKey: ['connector-activation', value.source_id] }),
          client.invalidateQueries({ queryKey: ['source-ingestion', value.source_id] }),
          ...(value.operation_id ? [client.invalidateQueries({ queryKey: ['operation', value.operation_id] })] : []),
        ]);
      });
      register(stream, attempt, 'ingestion.changed', (event) => {
        const value = parseEnvelope<IngestionEvent>(event.data);
        if (!value || !UUID_RE.test(value.source_id) || !UUID_RE.test(value.run_id)) { resync(true); return; }
        void Promise.all([
          client.invalidateQueries({ queryKey: ['sources', value.source_id] }),
          client.invalidateQueries({ queryKey: ['source-ingestion', value.source_id] }),
          client.invalidateQueries({ queryKey: ['ingestion-run', value.run_id] }),
          client.invalidateQueries({ queryKey: ['connector-activation', value.source_id] }),
        ]);
      });
      register(stream, attempt, 'knowledge.changed', (event) => {
        const value = parseEnvelope<KnowledgeEvent>(event.data);
        if (!value) { resync(true); return; }
        if (value.scope === 'index') {
          if (
            !value.index_generation_id || !UUID_RE.test(value.index_generation_id)
            || !['queued', 'running', 'active', 'failed', 'retired'].includes(value.index_status ?? '')
            || !Number.isSafeInteger(value.indexed_items) || (value.indexed_items ?? -1) < 0
            || !Number.isSafeInteger(value.failed_items) || (value.failed_items ?? -1) < 0
            || value.source_id != null || value.document_id != null || value.version != null || value.deleted !== false
          ) { resync(true); return; }
          void client.invalidateQueries({ queryKey: ['search-index'] });
          return;
        }
        if (
          (value.scope !== undefined && value.scope !== 'source')
          || !value.source_id || !UUID_RE.test(value.source_id)
          || (value.document_id && !UUID_RE.test(value.document_id))
          || value.index_generation_id != null || value.index_status != null
          || value.indexed_items != null || value.failed_items != null
        ) { resync(true); return; }
        if (value.document_id) queueDocumentUpdate(value.document_id);
        else queueDocumentUpdate(null);
      });
      const ownControlEvent = () => ownsStream();
      stream.addEventListener('resync_required', () => { if (ownControlEvent()) resync(true); });
      stream.addEventListener('auth_expired', () => {
        if (!ownControlEvent()) return;
        closeStream();
        window.dispatchEvent(new Event('bbd:unauthorized'));
      });
      stream.addEventListener('connection_unavailable', () => {
        if (!ownControlEvent()) return;
        closeStream();
        setStatus('unavailable');
        scheduleSnapshotRetry();
      });
    };
    setStatus('connecting');
    const initialAttempt = supersedeAttempt();
    void openSnapshot(false, initialAttempt, false);
    const authEnding = () => {
      active = false;
      cancelAttempt();
      closeStream();
      clearSnapshotRetry();
      cursorRef.current = '';
      queuedDocuments.current.clear();
      fullRefreshQueued.current = false;
      setNewDocumentCount(0);
      setDocumentRefreshRequired(false);
      setDocumentRefreshFailed(false);
    };
    window.addEventListener('bbd:auth-ending', authEnding);
    return () => {
      active = false;
      cancelAttempt();
      closeStream();
      clearSnapshotRetry();
      window.removeEventListener('bbd:auth-ending', authEnding);
    };
  }, [client, display.authGeneration, display.isCurrentGeneration, invalidateOperationalQueries, isAuthenticated, queueDocumentUpdate, sessionExpired]);

  const context = { status, newDocumentCount, documentRefreshRequired, documentRefreshFailed, consumeDocumentUpdates };
  const waitingForBarrier = isAuthenticated && barrierGeneration !== display.authGeneration;
  return <RealtimeContext.Provider value={context}>
    {waitingForBarrier
      ? <main className="shell"><div className="status-panel skeleton" aria-label={t('loadingWorkspace')} /></main>
      : children}
  </RealtimeContext.Provider>;
}
