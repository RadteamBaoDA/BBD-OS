import { WorkspaceShell } from '@/core/app-shell/workspace-shell';
import { DocumentDetail } from '@/modules/knowledge/document-detail';

/** Renders the route content and composes it with the shared shell or route-level loading behavior. */
export default async function DocumentPage({ params, searchParams }: { params: Promise<{ documentId: string }>; searchParams: Promise<{ version?: string }> }) {
  const { documentId } = await params;
  const { version } = await searchParams;
  const revision = Number(version);
  return <WorkspaceShell><DocumentDetail id={documentId} citedVersion={Number.isSafeInteger(revision) && revision > 0 ? revision : null} /></WorkspaceShell>;
}
