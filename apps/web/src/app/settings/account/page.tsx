import { WorkspaceShell } from '@/core/app-shell/workspace-shell';
import { GoogleLink } from '@/modules/account/google-link';

export default function AccountPage() {
  return <WorkspaceShell><GoogleLink /></WorkspaceShell>;
}
