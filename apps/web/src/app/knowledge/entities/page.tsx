import { WorkspaceShell } from '@/core/app-shell/workspace-shell';
import { EntityList } from '@/modules/knowledge/entity-list';

/** Renders the knowledge entities list route inside the workspace shell. */
export default function EntitiesPage() { return <WorkspaceShell><EntityList /></WorkspaceShell>; }
