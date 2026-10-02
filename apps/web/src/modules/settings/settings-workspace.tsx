'use client';

import { useTranslations } from 'next-intl';
import { SourceList } from '@/modules/sources/source-list';

/** Renders local settings navigation and the selected settings section. */
export function SettingsWorkspace() {
  const t = useTranslations('sources');
  return <section className="content-panel">
    <header className="section-heading settings-group-heading">
      <div><span className="brand">Settings</span><h1>{t('title')}</h1><p className="muted">{t('description')}</p></div>
    </header>
    <SourceList />
  </section>;
}
