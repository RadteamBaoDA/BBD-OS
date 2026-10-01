'use client';

import { useTranslations } from 'next-intl';

export type ApiConnectionStatus = 'connecting' | 'reconnecting' | 'unavailable' | 'connected' | 'expired';

export function ConnectionFooter({ apiStatus, onRetry, retrying = false }: { apiStatus: ApiConnectionStatus; onRetry?: () => void; retrying?: boolean }) {
  const t = useTranslations('shell');
  return <footer className="connection-footer" aria-label={t('connectionStatus')}>
    <span role="status" aria-live="polite">{t('api')}: {apiStatus === 'expired' ? t('sessionExpired') : t(apiStatus)}</span>
    {apiStatus !== 'connected' && onRetry && <button type="button" className="text-button" disabled={retrying} onClick={onRetry}>{retrying ? t('reconnecting') : t('retryApi')}</button>}
    <span>{t('realtime')}: {t('unavailable')} · {t('realtimeNotConfigured')}</span>
    <small>{t('sourceFreshnessNote')}</small>
  </footer>;
}
