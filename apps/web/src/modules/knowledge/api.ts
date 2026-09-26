import { apiRequest, csrfHeaders } from '@/core/api';

export type Document = {
  id: string; source_id: string; external_id: string | null; title: string;
  content_type: string | null; mime_type: string | null; raw_uri: string | null;
  canonical_url: string | null; author: string | null; metadata: Record<string, unknown>;
  current_version: number; content_hash: string; published_at: string | null;
  observed_at: string | null; language: string | null; created_at: string; updated_at: string;
};
export type DocumentVersion = { id: string; document_id: string; version_number: number; content: string; content_hash: string; observed_at: string; created_at: string };
export type DocumentPage = { items: Document[]; next_cursor: string | null };
export type VersionPage = { items: DocumentVersion[]; next_cursor: string | null };
export const documentKeys = { all: ['documents'] as const, detail: (id: string) => ['documents', id] as const, versions: (id: string) => ['documents', id, 'versions'] as const };

export function listDocuments(cursor?: string) { return apiRequest<DocumentPage>(`/api/v1/documents?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`); }
export function getDocument(id: string) { return apiRequest<Document>(`/api/v1/documents/${id}`); }
export function getVersion(id: string, number: number) { return apiRequest<DocumentVersion>(`/api/v1/documents/${id}/versions/${number}`); }
export function listVersions(id: string, cursor?: string) { return apiRequest<VersionPage>(`/api/v1/documents/${id}/versions?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`); }
export function createDocument(payload: { source_id: string; title: string; content: string }, csrfToken: string) { return apiRequest<Document>('/api/v1/documents', { method: 'POST', headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) }, body: JSON.stringify(payload) }); }
export function updateDocument(id: string, payload: { title: string; metadata: Record<string, unknown> }, csrfToken: string) { return apiRequest<Document>(`/api/v1/documents/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) }, body: JSON.stringify(payload) }); }
export function updateContent(id: string, content: string, expectedVersion: number, csrfToken: string) { return apiRequest<Document>(`/api/v1/documents/${id}/content`, { method: 'PUT', headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) }, body: JSON.stringify({ content, expected_version: expectedVersion }) }); }
export function deleteDocument(id: string, csrfToken: string) { return apiRequest<void>(`/api/v1/documents/${id}`, { method: 'DELETE', headers: csrfHeaders(csrfToken) }); }
