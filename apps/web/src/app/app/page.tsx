'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { WorkspaceShell } from '@/core/app-shell/workspace-shell';

/** Renders the authenticated application dashboard route. */
export default function AppPage() {
  const t = useTranslations('shell');
  return <WorkspaceShell><section className="content-panel"><span className="brand">BBD-OS</span><h1>{t('dashboardTitle')}</h1><p className="muted">{t('dashboardUnavailableDetail')}</p><div className="form-actions"><Link className="button" href="/knowledge/documents">{t('openDocuments')}</Link><Link className="button secondary" href="/search">{t('openSearch')}</Link></div></section></WorkspaceShell>;
}
