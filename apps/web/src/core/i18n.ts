export const appLocaleIds = ['en-us', 'vi-vi'] as const;
export type AppLocaleId = (typeof appLocaleIds)[number];
export type ThemePreference = 'light' | 'dark' | 'system';

const formattingLocales: Record<AppLocaleId, string> = {
  'en-us': 'en-US',
  'vi-vi': 'vi-VN',
};

export function normalizeFormattingLocale(locale: AppLocaleId): string {
  return formattingLocales[locale];
}

export function formatDateTime(value: string | Date, locale: AppLocaleId, timezone: string): string {
  return new Intl.DateTimeFormat(normalizeFormattingLocale(locale), {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: timezone,
  }).format(value instanceof Date ? value : new Date(value));
}
