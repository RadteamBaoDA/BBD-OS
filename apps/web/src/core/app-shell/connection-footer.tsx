'use client';

import { useTranslations } from 'next-intl';
import type { RealtimeStatus } from '@/core/realtime-provider';

export type ApiConnectionStatus = 'connecting' | 'reconnecting' | 'unavailable' | 'connected' | 'expired';

/** Renders separate API and realtime health states and exposes the supplied retry action while it is available. */
export function ConnectionFooter({ apiStatus, realtimeStatus, onRetry, retrying = false }: { apiStatus: ApiConnectionStatus; realtimeStatus: RealtimeStatus; onRetry?: () => void; retrying?: boolean }) {
  const t = useTranslations('shell');
  return <footer className="connection-footer" aria-label={t('connectionStatus')}>
    <span role="status" aria-live="polite">{t('api')}: {apiStatus === 'expired' ? t('sessionExpired') : t(apiStatus)}</span>
    {apiStatus !== 'connected' && onRetry && <button type="button" className="text-button" disabled={retrying} onClick={onRetry}>{retrying ? t('reconnecting') : t('retryApi')}</button>}
    <span role="status" aria-live="polite">{t('realtime')}: {t(realtimeStatus === 'expired' ? 'sessionExpired' : realtimeStatus)}</span>
    <small>{t('sourceFreshnessNote')}</small>
  </footer>;
}
