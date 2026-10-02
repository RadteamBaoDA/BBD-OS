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
  stages: { stage_key: string; status: string; attempts: number; error_code: string | null; result_count: number | null; normalized_count: number; duplicate_count: number; skipped_count: number; failed_count: number; pending_count: number; updated_at: string }[];
  error_code: string | null;
  created_at: string;
  updated_at: string;
};
export type ConnectorConfig = {
  url?: string;
  feed_url?: string;
  js_render: boolean;
  max_pages: number;
  max_depth: number;
  timeout_seconds: number;
  items_path?: string;
  id_field?: string;
  title_field?: string;
  content_field?: string;
  updated_field?: string;
  timezone: string;
  schedule_interval_minutes: 15 | 30 | 60 | 360 | 1440;
};
export type ConnectorSettings = {
  expected_revision: number;
  configuration: ConnectorConfig;
  auth_method: 'none' | 'http_header';
  auth_header_name?: string;
};
export type DraftValidationRequest = ConnectorSettings & { expected_source_generation: number };
export type ConnectorActivation = {
  source_id: string;
  desired_revision: number;
  applied_revision: number;
  state: string;
  error_code: string | null;
  credential_recovery: string;
};
export type ConnectorConfiguration = {
  source_id: string;
  source_type: 'rss' | 'web' | 'api';
  source_generation: number;
  configuration: ConnectorConfig;
  expected_revision: number;
  auth_method: 'none' | 'http_header';
  auth_header_name: string | null;
  desired_enabled: boolean;
  activation_state: string;
  activation_error_code: string | null;
  provider_credential_configured: boolean;
  provider_credential_state: string | null;
};
export type DraftValidation = {
  source_id: string;
  source_generation: number;
  expected_revision: number;
  validated_at: string;
  validation_status: 'valid';
  checks: ('configuration' | 'public_url_policy')[];
};
export type ConnectorCatalogEntry = {
  provider_id: string;
  label: string;
  auth_methods: string[];
  scope_fields: string[];
  configuration_fields: string[];
  quota_limits: Record<string, number>;
  history_description: string | null;
  collection_modes: string[];
  supports_history: boolean;
  supports_edit: boolean;
  supports_delete: boolean;
  availability: 'available' | 'planned' | 'unavailable';
  unavailable_reason: string | null;
  unavailable_operations: string[];
};
export type SourceIngestion = { current_run: IngestionRun | null; items: IngestionRun[]; next_cursor: string | null };
export type PurgeOperation = { operation_id: string; source_id: string; status: string; error_code: string | null; created_at: string; updated_at: string };
export const sourceKeys = { all: ['sources'] as const, list: ['sources', 'list'] as const, detail: (id: string) => ['sources', id] as const };
export const connectorKeys = {
  catalog: ['connector-catalog'] as const,
  configuration: (id: string) => ['connector-configuration', id] as const,
  activation: (id: string) => ['connector-activation', id] as const,
  ingestion: (id: string) => ['source-ingestion', id] as const,
};

/** Lists source records in pages of 50 and includes the optional opaque cursor. */
export function listSources(cursor?: string) {
  return apiRequest<SourcePage>(`/api/v1/sources?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`);
}

/** Fetches one source by its identifier. */
export function getSource(id: string) { return apiRequest<Source>(`/api/v1/sources/${id}`); }

/** Creates a manual source with the supplied name and CSRF token. */
export function createManualSource(name: string, csrfToken: string) {
  return apiRequest<Source>('/api/v1/sources', { method: 'POST', headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) }, body: JSON.stringify({ type: 'manual', name }) });
}

/** Archives a source through the source DELETE endpoint using CSRF protection. */
export function archiveSource(id: string, csrfToken: string) {
  return apiRequest<void>(`/api/v1/sources/${id}`, { method: 'DELETE', headers: csrfHeaders(csrfToken) });
}

/** Requests source deletion with source data purge and returns the asynchronous purge operation. */
export function purgeSource(id: string, csrfToken: string) {
  return apiRequest<PurgeOperation>(`/api/v1/sources/${id}?with_data=true`, { method: 'DELETE', headers: csrfHeaders(csrfToken) });
}

/** Sets a source to active or paused, forwarding the abort signal and CSRF token. */
export function updateSourceStatus(id: string, status: 'active' | 'paused', csrfToken: string, signal?: AbortSignal) {
  return apiRequest<Source>(`/api/v1/sources/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) }, body: JSON.stringify({ status }), signal });
}

/** Fetches the connector catalog and forwards an optional abort signal. */
export function getConnectorCatalog(signal?: AbortSignal) {
  return apiRequest<ConnectorCatalogEntry[]>('/api/v1/connectors/catalog', { signal });
}

/** Creates a typed connector source with the supplied name, CSRF token, and optional abort signal. */
export function createConnectorSource(type: 'rss' | 'web' | 'api', name: string, csrfToken: string, signal?: AbortSignal) {
  return apiRequest<Source>('/api/v1/sources', { method: 'POST', headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) }, body: JSON.stringify({ type, name }), signal });
}

/** Fetches the connector configuration and forwards an optional abort signal. */
export function getConnectorConfiguration(id: string, signal?: AbortSignal) {
  return apiRequest<ConnectorConfiguration>(`/api/v1/connectors/${id}/configuration`, { signal });
}

/** Checks matching source configuration snapshots against every same-source revision and generation fence. */
export function connectorConfigurationIsAtLeast(
  candidate: ConnectorConfiguration,
  fences: readonly (ConnectorConfiguration | undefined)[],
) {
  return fences.every((fence) => !fence || fence.source_id !== candidate.source_id
    || (candidate.expected_revision >= fence.expected_revision && candidate.source_generation >= fence.source_generation));
}

/** Selects the newest snapshot that is not older than the other snapshots for the requested source. */
export function newestConnectorConfiguration(
  snapshots: readonly (ConnectorConfiguration | undefined)[],
  sourceId: string,
) {
  const candidates = snapshots.filter((value): value is ConnectorConfiguration => value?.source_id === sourceId);
  return candidates.find((candidate) => connectorConfigurationIsAtLeast(candidate, candidates)) ?? null;
}

/** Accepts the candidate when it satisfies all revision fences, otherwise falls back to the newest fenced snapshot. */
export function selectMonotonicConnectorConfiguration(
  candidate: ConnectorConfiguration,
  fences: readonly (ConnectorConfiguration | undefined)[],
) {
  return connectorConfigurationIsAtLeast(candidate, fences)
    ? candidate
    : newestConnectorConfiguration(fences, candidate.source_id);
}

/** Fetches connector configuration, rejects a mismatched source ID, and selects a result that does not regress local revision fences. */
export async function getMonotonicConnectorConfiguration(
  id: string,
  signal: AbortSignal | undefined,
  current: () => readonly (ConnectorConfiguration | undefined)[],
) {
  const incoming = await getConnectorConfiguration(id, signal);
  if (incoming.source_id !== id) throw new Error('connector_configuration_source_mismatch');
  const fences = current();
  return selectMonotonicConnectorConfiguration(incoming, fences)
    ?? [...fences].reverse().find((value) => value?.source_id === id) ?? incoming;
}

/** Submits a connector draft for validation and forwards an optional abort signal; it does not save the configuration. */
export function validateDraftConnector(id: string, settings: DraftValidationRequest, signal?: AbortSignal) {
  return apiRequest<DraftValidation>(`/api/v1/connectors/${id}/validate-draft`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings), signal });
}

/** Saves connector settings with CSRF protection and the optional abort signal. */
export function saveConnectorConfiguration(id: string, settings: ConnectorSettings, csrfToken: string, signal?: AbortSignal) {
  return apiRequest<ConnectorActivation>(`/api/v1/connectors/${id}/configuration`, { method: 'PUT', headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) }, body: JSON.stringify(settings), signal });
}

/** Fetches the connector activation state and forwards an optional abort signal. */
export function getConnectorActivation(id: string, signal?: AbortSignal) {
  return apiRequest<ConnectorActivation>(`/api/v1/connectors/${id}/activation`, { signal });
}

/** Activates a connector at the expected revision and either replaces or retains its credential according to the supplied secret. */
export function activateConnector(id: string, expectedRevision: number, secret: string | undefined, csrfToken: string, signal?: AbortSignal) {
  const secretAction = secret ? 'replace' : 'keep';
  return apiRequest<ConnectorActivation>(`/api/v1/connectors/${id}/activate`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) }, body: JSON.stringify({ expected_revision: expectedRevision, secret_action: secretAction, ...(secret ? { secret } : {}) }), signal });
}

/** Deactivates the connector using CSRF protection and the optional abort signal. */
export function deactivateConnector(id: string, csrfToken: string, signal?: AbortSignal) {
  return apiRequest<ConnectorActivation>(`/api/v1/connectors/${id}/deactivate`, { method: 'POST', headers: csrfHeaders(csrfToken), signal });
}

/** Removes the provider credential only at the supplied expected revision, using CSRF protection. */
export function removeProviderCredential(id: string, expectedRevision: number, csrfToken: string, signal?: AbortSignal) {
  return apiRequest<ConnectorActivation>(`/api/v1/connectors/${id}/credentials/provider?expected_revision=${expectedRevision}`, { method: 'DELETE', headers: csrfHeaders(csrfToken), signal });
}

/** Starts connector collection with CSRF protection and returns the accepted run or batch identifiers. */
export function triggerCollection(id: string, csrfToken: string) {
  return apiRequest<{ run_id: string | null; batch_id: string | null; status: string }>(`/api/v1/connectors/sources/${id}/collect`, { method: 'POST', headers: csrfHeaders(csrfToken) });
}

/** Fetches an ingestion run by ID. */
export function getRun(id: string) { return apiRequest<IngestionRun>(`/api/v1/ingestion/runs/${id}`); }

/** Lists a source’s ingestion runs in pages of 20 using the optional cursor. */
export function getSourceIngestion(id: string, cursor?: string) {
  return apiRequest<SourceIngestion>(`/api/v1/ingestion/sources/${id}/runs?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`);
}

/** Retries the selected ingestion stage using CSRF protection. */
export function retryRun(id: string, stageKey: string, csrfToken: string) {
  return apiRequest<{ run_id: string }>(`/api/v1/ingestion/runs/${id}/retry`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...csrfHeaders(csrfToken) }, body: JSON.stringify({ stage_key: stageKey }) });
}

/** Fetches a system operation by ID. */
export function getOperation(id: string) { return apiRequest<PurgeOperation>(`/api/v1/system/operations/${id}`); }
