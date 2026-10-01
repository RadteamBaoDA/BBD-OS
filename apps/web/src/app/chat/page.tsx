'use client';

import { useTranslations } from 'next-intl';
import { WorkspaceShell } from '@/core/app-shell/workspace-shell';

export default function ChatPage() {
  const t = useTranslations('shell');
  return <WorkspaceShell><section className="content-panel"><span className="brand">BBD-OS</span><h1>{t('chatTitle')}</h1><p className="muted">{t('chatUnavailableDetail')}</p></section></WorkspaceShell>;
}
