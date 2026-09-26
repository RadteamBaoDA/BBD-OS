'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

type Theme = 'light' | 'dark';
const ThemeContext = createContext<{ theme: Theme; setTheme: (theme: Theme) => void } | null>(null);

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error('Theme is unavailable');
  return value;
}

export function QueryProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>('light');
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { refetchOnWindowFocus: false, retry: false, staleTime: 10_000 },
        },
      }),
  );
  useEffect(() => { document.body.dataset.theme = theme; }, [theme]);
  return <QueryClientProvider client={client}><ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider></QueryClientProvider>;
}
