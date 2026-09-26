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
  created_at: string;
  updated_at: string;
};
export type SourcePage = { items: Source[]; next_cursor: string | null };
export const sourceKeys = { all: ['sources'] as const, list: ['sources', 'list'] as const };

export function listSources(cursor?: string) {
  return apiRequest<SourcePage>(`/api/v1/sources?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`);
}

export function getSource(id: string) { return apiRequest<Source>(`/api/v1/sources/${id}`); }

export function createManualSource(name: string, csrfToken: string) {
  return apiRequest<Source>('/api/v1/sources', { method: 'POST', headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) }, body: JSON.stringify({ type: 'manual', name }) });
}

export function archiveSource(id: string, csrfToken: string) {
  return apiRequest<Source>(`/api/v1/sources/${id}`, { method: 'DELETE', headers: csrfHeaders(csrfToken) });
}
