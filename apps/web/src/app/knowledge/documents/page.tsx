import { WorkspaceShell } from '@/core/app-shell/workspace-shell';
import { DocumentList } from '@/modules/knowledge/document-list';

/** Renders the knowledge documents list route inside the workspace shell. */
export default function DocumentsPage() { return <WorkspaceShell><DocumentList /></WorkspaceShell>; }
