import { apiRequest, csrfHeaders } from '@/core/api';

export type Source = {
  id: string;
  type: string;
  name: string;
  provider: string | null;
  status: 'active' | 'paused' | 'archived';
  local_only: boolean;
  last_sync_at: string | null;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error_code: string | null;
  collected_at: string | null;
  indexed_at: string | null;
  collection_error_code: string | null;
  processing_error_code: string | null;
  generation: number;
  retired_at: string | null;
  created_at: string;
  updated_at: string;
};
export type SourcePage = { items: Source[]; next_cursor: string | null };
export type IngestionRun = {
  run_id: string;
  source_id: string;
  status: 'queued' | 'running' | 'succeeded' | 'needs_ocr' | 'failed';
  stages: { stage_key: string; status: string; attempts: number; error_code: string | null; result_count: number | null; updated_at: string }[];
  error_code: string | null;
  created_at: string;
  updated_at: string;
};
export type PurgeOperation = { operation_id: string; source_id: string; status: string; error_code: string | null; created_at: string; updated_at: string };
export const sourceKeys = { all: ['sources'] as const, list: ['sources', 'list'] as const };

export function listSources(cursor?: string) {
  return apiRequest<SourcePage>(`/api/v1/sources?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`);
}

export function getSource(id: string) { return apiRequest<Source>(`/api/v1/sources/${id}`); }

export function createManualSource(name: string, csrfToken: string) {
  return apiRequest<Source>('/api/v1/sources', { method: 'POST', headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) }, body: JSON.stringify({ type: 'manual', name }) });
}

export function archiveSource(id: string, csrfToken: string) {
  return apiRequest<void>(`/api/v1/sources/${id}`, { method: 'DELETE', headers: csrfHeaders(csrfToken) });
}

export function purgeSource(id: string, csrfToken: string) {
  return apiRequest<PurgeOperation>(`/api/v1/sources/${id}?with_data=true`, { method: 'DELETE', headers: csrfHeaders(csrfToken) });
}

export function updateSourceStatus(id: string, status: 'active' | 'paused', csrfToken: string) {
  return apiRequest<Source>(`/api/v1/sources/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) }, body: JSON.stringify({ status }) });
}

export function createConnectorSource(type: 'rss' | 'web' | 'api', name: string, csrfToken: string) {
  return apiRequest<Source>('/api/v1/sources', { method: 'POST', headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) }, body: JSON.stringify({ type, name }) });
}

export function configureConnector(id: string, configuration: Record<string, unknown>, csrfToken: string) {
  return apiRequest<{ source_id: string; url: string }>(`/api/v1/connectors/sources/${id}/configuration`, { method: 'PUT', headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) }, body: JSON.stringify(configuration) });
}

export function validateConnector(id: string, token: string) {
  return apiRequest<{ source_id: string; url: string }>(`/api/v1/connectors/sources/${id}/validate`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
}

export function issueCollectorCredential(id: string, csrfToken: string) {
  return apiRequest<{ source_id: string; token: string }>(`/api/v1/ingestion/sources/${id}/collector-credential`, { method: 'POST', headers: csrfHeaders(csrfToken) });
}

export function triggerCollection(id: string, csrfToken: string) {
  return apiRequest<{ run_id: string; batch_id: string | null; status: string }>(`/api/v1/connectors/sources/${id}/collect`, { method: 'POST', headers: csrfHeaders(csrfToken) });
}

export function getRun(id: string) { return apiRequest<IngestionRun>(`/api/v1/ingestion/runs/${id}`); }

export function retryRun(id: string, csrfToken: string) {
  return apiRequest<{ run_id: string }>(`/api/v1/ingestion/runs/${id}/retry`, { method: 'POST', headers: csrfHeaders(csrfToken) });
}

export function getOperation(id: string) { return apiRequest<PurgeOperation>(`/api/v1/system/operations/${id}`); }
