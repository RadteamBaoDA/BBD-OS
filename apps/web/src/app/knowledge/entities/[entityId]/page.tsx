import { WorkspaceShell } from '@/core/app-shell/workspace-shell';
import { EntityDetail } from '@/modules/knowledge/entity-detail';

/** Renders the route content and composes it with the shared shell or route-level loading behavior. */
export default function EntityDetailPage() { return <WorkspaceShell><EntityDetail /></WorkspaceShell>; }
