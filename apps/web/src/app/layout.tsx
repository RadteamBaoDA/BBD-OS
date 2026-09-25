import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { QueryProvider } from '@/core/query-provider';
import './globals.css';

export const metadata: Metadata = {
  title: 'BBD-OS',
  description: 'Private personal intelligence workspace',
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
