'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NextIntlClientProvider } from 'next-intl';
import { ThemeProvider, useTheme } from 'next-themes';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { AppLocaleId, normalizeFormattingLocale } from '@/core/i18n';
import { messages } from '@/core/messages';
import { OwnerPreferences, PreferenceValues } from '@/core/preferences';

function englishMessageFallback(namespace: string | undefined, key: string): string {
  let value: unknown = messages['en-us'];
  for (const part of [...(namespace?.split('.') ?? []), ...key.split('.')]) {
    value = value && typeof value === 'object' ? (value as Record<string, unknown>)[part] : undefined;
  }
  return typeof value === 'string' ? value : [namespace, key].filter(Boolean).join('.');
}

type PreviewState = { value: PreferenceValues; generation: number } | null;

type DisplayPreferenceContextValue = {
  locale: AppLocaleId;
  timezone: string;
  confirmedPreferences: OwnerPreferences | null;
  preview: PreferenceValues | null;
  authGeneration: number;
  confirmPreferences: (value: OwnerPreferences, generation: number) => void;
  setPreview: (value: PreferenceValues | null, generation: number) => void;
  endAuthSession: () => void;
  isCurrentGeneration: (generation: number) => boolean;
};

const DisplayPreferenceContext = createContext<DisplayPreferenceContextValue | null>(null);

export function useDisplayPreferences() {
  const value = useContext(DisplayPreferenceContext);
  if (!value) throw new Error('Display preferences are unavailable');
  return value;
}

export function QueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(
    () => new QueryClient({
      defaultOptions: {
        queries: { refetchOnWindowFocus: false, retry: false, staleTime: 10_000 },
      },
    }),
  );
  return <QueryClientProvider client={client}>
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <DisplayPreferencesProvider>{children}</DisplayPreferencesProvider>
    </ThemeProvider>
  </QueryClientProvider>;
}

function DisplayPreferencesProvider({ children }: { children: ReactNode }) {
  const { setTheme } = useTheme();
  const themeSetterRef = useRef(setTheme);
  themeSetterRef.current = setTheme;
  const [confirmedPreferences, setConfirmedPreferences] = useState<OwnerPreferences | null>(null);
  const confirmedRef = useRef<OwnerPreferences | null>(null);
  const [bootstrapValues, setBootstrapValues] = useState<PreferenceValues>({ theme: 'system', locale: 'en-us', timezone: 'Asia/Ho_Chi_Minh' });
  const bootstrapRef = useRef(bootstrapValues);
  const [browserLocale, setBrowserLocale] = useState<AppLocaleId>('en-us');
  const [previewState, setPreviewState] = useState<PreviewState>(null);
  const [authGeneration, setAuthGeneration] = useState(0);
  const generationRef = useRef(0);
  useEffect(() => {
    const lang = navigator.language.toLowerCase();
    setBrowserLocale(lang.startsWith('vi') ? 'vi-vi' : 'en-us');
  }, []);

  const confirmedValues = useMemo<PreferenceValues>(() => confirmedPreferences
    ? { ...confirmedPreferences, locale: confirmedPreferences.persisted ? confirmedPreferences.locale : browserLocale }
    : { ...bootstrapValues, locale: browserLocale }, [confirmedPreferences, bootstrapValues, browserLocale]);
  const activePreview = previewState?.generation === authGeneration ? previewState.value : null;
  const effective = activePreview ?? confirmedValues;

  useEffect(() => {
    document.documentElement.lang = normalizeFormattingLocale(effective.locale);
  }, [effective.locale]);

  useEffect(() => {
    if (confirmedPreferences) themeSetterRef.current(effective.theme);
  }, [effective.theme, Boolean(confirmedPreferences)]);

  const isCurrentGeneration = useCallback((generation: number) => generationRef.current === generation, []);
  const confirmPreferences = useCallback((value: OwnerPreferences, generation: number) => {
    if (generationRef.current !== generation) return;
    confirmedRef.current = value;
    setConfirmedPreferences(value);
    const next = { theme: value.theme, locale: value.locale, timezone: value.timezone };
    bootstrapRef.current = next;
    setBootstrapValues(next);
  }, []);
  const setPreview = useCallback((value: PreferenceValues | null, generation: number) => {
    if (generationRef.current !== generation) return;
    setPreviewState(value ? { value, generation } : (current) => current?.generation === generation ? null : current);
  }, []);
  const endAuthSession = useCallback(() => {
    const retained = confirmedRef.current
      ? { theme: confirmedRef.current.theme, locale: confirmedRef.current.locale, timezone: confirmedRef.current.timezone }
      : bootstrapRef.current;
    themeSetterRef.current(retained.theme);
    bootstrapRef.current = retained;
    setBootstrapValues(retained);
    confirmedRef.current = null;
    setConfirmedPreferences(null);
    setPreviewState(null);
    generationRef.current += 1;
    setAuthGeneration(generationRef.current);
  }, []);

  return <DisplayPreferenceContext.Provider value={{
        locale: effective.locale,
        timezone: effective.timezone,
        confirmedPreferences,
        preview: activePreview,
        authGeneration,
        confirmPreferences,
        setPreview,
        endAuthSession,
        isCurrentGeneration,
  }}>
    <NextIntlClientProvider locale={normalizeFormattingLocale(effective.locale)} messages={messages[effective.locale]} getMessageFallback={({ namespace, key }) => englishMessageFallback(namespace, key)}>
      {children}
    </NextIntlClientProvider>
  </DisplayPreferenceContext.Provider>;
}
