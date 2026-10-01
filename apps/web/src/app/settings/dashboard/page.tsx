'use client';

import { useTranslations } from 'next-intl';
import { WorkspaceShell } from '@/core/app-shell/workspace-shell';

export default function DashboardSettingsPage() {
  const t = useTranslations('shell');
  return <WorkspaceShell><section className="content-panel"><span className="brand">{t('dashboardSettingsTitle')}</span><h1>{t('dashboardSettingsTitle')}</h1><p className="muted">{t('dashboardSettingsIntro')}</p></section></WorkspaceShell>;
}
