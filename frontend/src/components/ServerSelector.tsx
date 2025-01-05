'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { getBotServers } from '@/lib/api';
import { useServerStore, useThemeStore } from '@/lib/store';
import Image from 'next/image';

interface Server {
  id: string;
  name: string;
  icon: string | null;
}

export default function ServerSelector() {
  const [servers, setServers] = useState<Server[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const { data: session } = useSession();
  const { selectedServer, setSelectedServer } = useServerStore();
  const theme = useThemeStore((state) => state.theme);
  const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  useEffect(() => {
    async function fetchServers() {
      try {
        setLoading(true);
        setError(null);
        const data = await getBotServers();
        setServers(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch servers');
        console.error('Error fetching servers:', err);
      } finally {
        setLoading(false);
      }
    }

    if (session?.accessToken) {
      fetchServers();
    }
  }, [session?.accessToken]);

  const handleServerSelect = (server: Server) => {
    setSelectedServer(server);
    router.push(`/server/${server.id}/cases`);
  };

  if (!session) {
    return null;
  }

  return (
    <div className="w-64 h-screen bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700">
      <div className="p-4">
        <h2 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
          Select Server
        </h2>
        <div className="h-[calc(100vh-8rem)] overflow-y-auto">
          {loading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center space-x-4 mb-4 animate-pulse">
                <div className="h-10 w-10 rounded-full bg-gray-200 dark:bg-gray-700" />
                <div className="h-4 w-32 bg-gray-200 dark:bg-gray-700 rounded" />
              </div>
            ))
          ) : error ? (
            <div className="text-red-500 dark:text-red-400 text-sm">{error}</div>
          ) : servers.length === 0 ? (
            <div className="text-gray-500 dark:text-gray-400 text-sm">
              No servers available
            </div>
          ) : (
            <div className="space-y-2">
              {servers.map((server) => (
                <button
                  key={server.id}
                  onClick={() => handleServerSelect(server)}
                  className={`w-full flex items-center space-x-3 p-2 rounded-lg transition-colors duration-200 ${
                    selectedServer?.id === server.id
                      ? 'bg-gray-100 dark:bg-gray-700'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-700'
                  }`}
                >
                  {server.icon ? (
                    <Image
                      src={`https://cdn.discordapp.com/icons/${server.id}/${server.icon}.png`}
                      alt={server.name}
                      width={40}
                      height={40}
                      className="rounded-full"
                    />
                  ) : (
                    <div className="w-10 h-10 rounded-full bg-gray-200 dark:bg-gray-600 flex items-center justify-center">
                      <span className="text-gray-500 dark:text-gray-400 text-sm">
                        {server.name.charAt(0)}
                      </span>
                    </div>
                  )}
                  <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
                    {server.name}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
} 