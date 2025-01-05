'use client';

import { useSession } from 'next-auth/react';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { DiscordLogo } from '@phosphor-icons/react';

export default function Home() {
  const { data: session, status } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (status === 'authenticated') {
      router.push('/dashboard');
    }
  }, [status, router]);

  if (status === 'loading') {
    return (
      <div className="flex items-center justify-center min-h-[calc(100vh-4rem)]">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-4rem)] text-center">
      <h1 className="text-4xl font-bold mb-4">Welcome to SDHS Bot Dashboard</h1>
      <p className="text-xl text-gray-600 dark:text-gray-400 mb-8 max-w-2xl">
        Manage your Discord server with powerful moderation tools, statistics, and
        more. Sign in with Discord to get started.
      </p>
      <div className="flex flex-col items-center space-y-4">
        <div className="flex items-center space-x-4">
          <div className="flex items-center justify-center w-12 h-12 rounded-lg bg-indigo-100 dark:bg-indigo-900">
            <DiscordLogo className="w-6 h-6 text-indigo-600 dark:text-indigo-400" weight="fill" />
          </div>
          <div className="text-left">
            <h3 className="font-semibold">Discord Integration</h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Seamlessly connect with your Discord servers
            </p>
          </div>
        </div>
      </div>
    </div>
  );
} 