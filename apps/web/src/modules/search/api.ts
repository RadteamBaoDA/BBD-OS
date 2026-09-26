import { apiRequest } from '@/core/api';

export type SearchHit = {
  document_id: string;
  document_version_id: string;
  version_number: number;
  chunk_id: string;
  title: string;
  excerpt: string;
  source: { id: string; name: string; type: string };
  observed_at: string | null;
  published_at: string | null;
  content_type: string | null;
  citation: { sourceType: 'document'; sourceId: string; documentId: string; chunkId: string; title: string; url: string | null; observedAt: string | null; quote: string };
};

export type SearchResponse = { items: SearchHit[]; next_cursor: string | null; effective_mode: 'lexical' | 'hybrid'; warnings: string[] };
export type SearchIndexStatus = { run_id: string | null; status: string; model_id: string | null; dimensions: number | null; indexed_items: number; failed_items: number };
export type SearchFilters = { source_ids: string[]; date_from: string | null; date_to: string | null; content_types: string[] };

export function searchDocuments(query: string, filters: SearchFilters, mode: 'lexical' | 'hybrid', cursor?: string) {
  return apiRequest<SearchResponse>('/api/v1/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, filters, mode, limit: 20, cursor: cursor ?? null }),
  });
}

export function getSearchIndexStatus() { return apiRequest<SearchIndexStatus>('/api/v1/search/index'); }
