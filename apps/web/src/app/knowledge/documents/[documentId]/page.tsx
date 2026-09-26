import { WorkspaceShell } from '@/core/app-shell/workspace-shell';
import { DocumentDetail } from '@/modules/knowledge/document-detail';

export default async function DocumentPage({ params, searchParams }: { params: Promise<{ documentId: string }>; searchParams: Promise<{ version?: string }> }) {
  const { documentId } = await params;
  const { version } = await searchParams;
  const revision = Number(version);
  return <WorkspaceShell><DocumentDetail id={documentId} citedVersion={Number.isSafeInteger(revision) && revision > 0 ? revision : null} /></WorkspaceShell>;
}
