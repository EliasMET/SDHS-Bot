'use client';

import { Inter } from 'next/font/google';
import { Providers } from '../providers';
import { Layout } from './Layout';

const inter = Inter({ subsets: ['latin'] });

export function RootLayoutClient({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <head>
        <meta name="color-scheme" content="light dark" />
      </head>
      <body className={`${inter.className} h-full antialiased`}>
        <Providers>
          <Layout>{children}</Layout>
        </Providers>
      </body>
    </html>
  );
} 