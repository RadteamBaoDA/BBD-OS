import { Suspense } from 'react';
import { WorkspaceShell } from '@/core/app-shell/workspace-shell';
import { SearchPage } from '@/modules/search/search-page';

export default function Page() { return <WorkspaceShell><Suspense fallback={<div className="content-panel skeleton" aria-label="Loading search" />}><SearchPage /></Suspense></WorkspaceShell>; }
