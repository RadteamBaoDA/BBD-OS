'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ApiError } from '@/core/api';
import { useWorkspaceSession } from '@/core/app-shell/workspace-shell';
import { configureConnector, createConnectorSource, issueCollectorCredential, validateConnector } from './api';

export function ConnectorSetup({ onSaved }: { onSaved: () => void }) {
  const { csrfToken } = useWorkspaceSession();
  const [type, setType] = useState<'rss' | 'web' | 'api'>('rss');
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [itemsPath, setItemsPath] = useState('items');
  const [idField, setIdField] = useState('id');
  const [contentField, setContentField] = useState('content');
  const [token, setToken] = useState('');
  const [sourceId, setSourceId] = useState('');
  const [sourceGeneration, setSourceGeneration] = useState(0);
  const [connectorRevision, setConnectorRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [validated, setValidated] = useState(false);

  async function save() {
    setBusy(true);
    setError('');
    try {
      const source = await createConnectorSource(type, name.trim(), csrfToken);
      const config = type === 'rss' ? { feed_url: url } : type === 'web' ? { url } : {
        url, items_path: itemsPath, id_field: idField, content_field: contentField,
      };
      const configured = await configureConnector(source.id, config, csrfToken);
      const credential = await issueCollectorCredential(source.id, csrfToken);
      setSourceId(source.id);
      setSourceGeneration(configured.source_generation);
      setConnectorRevision(configured.connector_revision);
      setToken(credential.token);
      await validateConnector(source.id, credential.token, configured.source_generation, configured.connector_revision);
      setValidated(true);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not configure this connector.');
    } finally {
      setBusy(false);
    }
  }

  async function retryValidation() {
    setBusy(true);
    setError('');
    try {
      await validateConnector(sourceId, token, sourceGeneration, connectorRevision);
      setValidated(true);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not validate this source.');
    } finally {
      setBusy(false);
    }
  }

  if (token) return <section className="sub-panel" aria-live="polite">
    <h2>Managed connector setup</h2>
    {validated ? <p role="status">Source validation succeeded.</p> : <p className="error" role="alert">Source validation failed. The one-time token is still shown below; correct the connector or provider setup and validate again. {error}</p>}
    <p>This panel validates a source and issues its scoped collector token, but does not yet connect to managed activation.</p>
    <p><strong>Source ID</strong></p><pre>{sourceId}</pre>
    <p><strong>Collector token · shown once; no workflow is active yet</strong></p><pre>{token}</pre>
    <p>Do not configure a global source ID or create credentials and workflows directly in n8n. Use the BBD-OS source editor when its activation controls are available.</p>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="form-actions">{!validated && <Button disabled={busy} onClick={retryValidation}>Retry validation</Button>}<Button onClick={onSaved}>Done</Button></div>
  </section>;

  return <section className="sub-panel">
    <h2>Set up a connector</h2>
    <p className="muted">n8n stores provider credentials securely; BBD-OS manages their references and workflow activation.</p>
    <div className="form">
      <div className="field"><Label htmlFor="connector-type">Type</Label><select id="connector-type" className="input" value={type} onChange={(event) => setType(event.target.value as typeof type)}><option value="rss">RSS / Atom</option><option value="web">Web page</option><option value="api">REST API</option></select></div>
      <div className="field"><Label htmlFor="connector-name">Name</Label><Input id="connector-name" maxLength={200} value={name} onChange={(event) => setName(event.target.value)} /></div>
      <div className="field"><Label htmlFor="connector-url">{type === 'rss' ? 'Feed URL' : 'URL'}</Label><Input id="connector-url" type="url" required value={url} onChange={(event) => setUrl(event.target.value)} /></div>
      {type === 'api' && <>
        <div className="field"><Label htmlFor="connector-items">Items path</Label><Input id="connector-items" value={itemsPath} onChange={(event) => setItemsPath(event.target.value)} /></div>
        <div className="field"><Label htmlFor="connector-id">Record ID field</Label><Input id="connector-id" value={idField} onChange={(event) => setIdField(event.target.value)} /></div>
        <div className="field"><Label htmlFor="connector-content">Content field</Label><Input id="connector-content" value={contentField} onChange={(event) => setContentField(event.target.value)} /></div>
      </>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="form-actions"><Button disabled={busy || !name.trim() || !url.trim()} onClick={save}>{busy ? 'Validating…' : 'Validate and continue'}</Button><Button type="button" className="secondary" onClick={onSaved}>Cancel</Button></div>
    </div>
  </section>;
}
