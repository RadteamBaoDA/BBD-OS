import type { NextConfig } from 'next';
import createNextIntlPlugin from 'next-intl/plugin';

const nextConfig: NextConfig = {
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.API_INTERNAL_URL ?? 'http://localhost:8000'}/api/:path*`,
      },
      { source: '/health', destination: `${process.env.API_INTERNAL_URL ?? 'http://localhost:8000'}/health` },
    ];
  },
};

const withNextIntl = createNextIntlPlugin('./src/core/i18n-request.ts');

export default withNextIntl(nextConfig);
