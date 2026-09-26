import { WorkspaceShell } from '@/core/app-shell/workspace-shell';
import { DocumentDetail } from '@/modules/knowledge/document-detail';

export default async function DocumentPage({ params }: { params: Promise<{ documentId: string }> }) {
  const { documentId } = await params;
  return <WorkspaceShell><DocumentDetail id={documentId} /></WorkspaceShell>;
}
