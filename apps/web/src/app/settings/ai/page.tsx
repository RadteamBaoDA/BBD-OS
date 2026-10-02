import { WorkspaceShell } from '@/core/app-shell/workspace-shell';
import { AISettingsWorkspace } from '@/modules/settings/ai-settings';

/** Renders AI and Ommi Router settings within the workspace shell. */
export default function AISettingsPage() { return <WorkspaceShell><AISettingsWorkspace /></WorkspaceShell>; }
