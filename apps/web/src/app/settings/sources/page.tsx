import { WorkspaceShell } from '@/core/app-shell/workspace-shell';
import { SettingsWorkspace } from '@/modules/settings/settings-workspace';

/** Renders data-source settings within the workspace shell. */
export default function SettingsSourcesPage() { return <WorkspaceShell><SettingsWorkspace /></WorkspaceShell>; }
