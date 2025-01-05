'use client';

import { useSession } from 'next-auth/react';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { useServerStore } from '@/stores/serverStore';
import { useQuery } from '@tanstack/react-query';
import { getStats } from '@/lib/api';
import Link from 'next/link';
import {
  ChartLine,
  Gavel,
  Users,
  ClockCounterClockwise,
} from '@phosphor-icons/react';

export default function Dashboard() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const selectedServer = useServerStore((state) => state.selectedServer);

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/sign-in');
    }
  }, [status, router]);

  const { data: stats, isLoading } = useQuery({
    queryKey: ['stats', selectedServer?.id],
    queryFn: () => getStats(selectedServer!.id),
    enabled: !!selectedServer,
  });

  if (status === 'loading' || !selectedServer) {
    return (
      <div className="flex items-center justify-center min-h-[calc(100vh-4rem)]">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold mb-2">{selectedServer.name}</h1>
        <p className="text-gray-600 dark:text-gray-400">
          Manage your server settings, view statistics, and handle moderation cases.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Link
          href="/cases"
          className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow-sm hover:shadow-md transition-shadow"
        >
          <div className="flex items-center space-x-4">
            <div className="p-3 bg-indigo-100 dark:bg-indigo-900 rounded-lg">
              <Gavel className="w-6 h-6 text-indigo-600 dark:text-indigo-400" weight="fill" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Cases</h2>
              <p className="text-gray-600 dark:text-gray-400">
                {isLoading ? 'Loading...' : `${stats?.total_cases || 0} total`}
              </p>
            </div>
          </div>
        </Link>

        <Link
          href="/stats"
          className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow-sm hover:shadow-md transition-shadow"
        >
          <div className="flex items-center space-x-4">
            <div className="p-3 bg-green-100 dark:bg-green-900 rounded-lg">
              <ChartLine className="w-6 h-6 text-green-600 dark:text-green-400" weight="fill" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Statistics</h2>
              <p className="text-gray-600 dark:text-gray-400">View insights</p>
            </div>
          </div>
        </Link>

        <div className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow-sm">
          <div className="flex items-center space-x-4">
            <div className="p-3 bg-blue-100 dark:bg-blue-900 rounded-lg">
              <Users className="w-6 h-6 text-blue-600 dark:text-blue-400" weight="fill" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Active Cases</h2>
              <p className="text-gray-600 dark:text-gray-400">
                {isLoading ? 'Loading...' : `${stats?.active_cases || 0} active`}
              </p>
            </div>
          </div>
        </div>

        <div className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow-sm">
          <div className="flex items-center space-x-4">
            <div className="p-3 bg-purple-100 dark:bg-purple-900 rounded-lg">
              <ClockCounterClockwise className="w-6 h-6 text-purple-600 dark:text-purple-400" weight="fill" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Recent Activity</h2>
              <p className="text-gray-600 dark:text-gray-400">Last 24 hours</p>
            </div>
          </div>
        </div>
      </div>

      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow-sm">
            <h2 className="text-lg font-semibold mb-4">Cases by Type</h2>
            <div className="space-y-2">
              {Object.entries(stats.cases_by_type).map(([type, count]) => (
                <div key={type} className="flex justify-between items-center">
                  <span className="text-gray-600 dark:text-gray-400 capitalize">
                    {type.toLowerCase()}
                  </span>
                  <span className="font-medium">{count}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow-sm">
            <h2 className="text-lg font-semibold mb-4">Recent Cases</h2>
            <div className="space-y-2">
              {Object.entries(stats.cases_over_time)
                .slice(-5)
                .map(([date, count]) => (
                  <div key={date} className="flex justify-between items-center">
                    <span className="text-gray-600 dark:text-gray-400">
                      {new Date(date).toLocaleDateString()}
                    </span>
                    <span className="font-medium">{count}</span>
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
} 