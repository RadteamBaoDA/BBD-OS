import type { AppLocaleId, ThemePreference } from '@/core/i18n';

export type PreferenceValues = {
  theme: ThemePreference;
  locale: AppLocaleId;
  timezone: string;
};

export type OwnerPreferences = PreferenceValues & {
  configuration_revision: number;
  persisted: boolean;
};
