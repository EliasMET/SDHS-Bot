'use client';

import { useSession } from 'next-auth/react';
import { useQuery } from '@tanstack/react-query';
import { getCommandStats } from '@/lib/api';
import { useThemeStore } from '@/lib/store';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { motion } from 'framer-motion';

interface CommandStat {
  command: string;
  total_uses: number;
  successful_uses: number;
  failed_uses: number;
  unique_users: number;
  average_response_time: number;
}

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 }
};

export default function Stats() {
  const { data: session } = useSession();
  const selectedServer = useThemeStore((state) => state.selectedServer);
  const isDarkMode = useThemeStore((state) => state.isDarkMode);

  const { data: stats, isLoading, error } = useQuery({
    queryKey: ['commandStats', selectedServer?.id],
    queryFn: () => getCommandStats(selectedServer!.id),
    enabled: !!selectedServer && !!session,
    gcTime: 5 * 60 * 1000, // 5 minutes
    staleTime: 60 * 1000, // 1 minute
    retry: 2,
  });

  if (!session) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center"
      >
        <h1 className={`text-4xl font-bold tracking-tight mb-4 ${
          isDarkMode ? 'text-white' : 'text-gray-900'
        }`}>
          Access Denied
        </h1>
        <p className={`text-lg leading-8 ${isDarkMode ? 'text-gray-300' : 'text-gray-600'}`}>
          Please sign in to view statistics.
        </p>
      </motion.div>
    );
  }

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="md:flex md:items-center md:justify-between"
      >
        <div className="min-w-0 flex-1">
          <h2 className={`text-2xl font-bold leading-7 sm:truncate sm:text-3xl sm:tracking-tight ${
            isDarkMode ? 'text-white' : 'text-gray-900'
          }`}>
            Command Statistics
          </h2>
        </div>
      </motion.div>

      {!selectedServer ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className={`text-center p-12 rounded-lg border-2 border-dashed ${
            isDarkMode ? 'text-gray-400 border-gray-700' : 'text-gray-600 border-gray-200'
          }`}
        >
          <p className="text-lg font-medium mb-2">Select a Server</p>
          <p className="text-sm">Choose a server from the dropdown above to view its command statistics.</p>
        </motion.div>
      ) : error ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className={`text-center p-12 rounded-lg border-2 border-dashed ${
            isDarkMode ? 'text-red-400 border-red-700' : 'text-red-600 border-red-200'
          }`}
        >
          <p className="text-lg font-medium mb-2">Error Loading Statistics</p>
          <p className="text-sm">There was an error loading the command statistics. Please try again later.</p>
        </motion.div>
      ) : isLoading ? (
        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
        >
          {Array.from({ length: 6 }).map((_, i) => (
            <motion.div key={i} variants={item}>
              <Card>
                <CardHeader>
                  <Skeleton className="h-4 w-1/3" />
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-4 w-2/3" />
                    <Skeleton className="h-4 w-3/4" />
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      ) : stats?.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className={`text-center p-12 rounded-lg border-2 border-dashed ${
            isDarkMode ? 'text-gray-400 border-gray-700' : 'text-gray-600 border-gray-200'
          }`}
        >
          <p className="text-lg font-medium mb-2">No Statistics Available</p>
          <p className="text-sm">No command usage data has been recorded for this server yet.</p>
        </motion.div>
      ) : (
        <motion.div
          variants={container}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
        >
          {stats?.map((stat: CommandStat) => (
            <motion.div key={stat.command} variants={item}>
              <Card>
                <CardHeader>
                  <CardTitle>{stat.command}</CardTitle>
                  <CardDescription>
                    Used by {stat.unique_users} unique users
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span>Total Uses:</span>
                      <span className="font-semibold">{stat.total_uses}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Successful:</span>
                      <span className="text-green-600 dark:text-green-400">
                        {stat.successful_uses}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Failed:</span>
                      <span className="text-red-600 dark:text-red-400">
                        {stat.failed_uses}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Avg Response Time:</span>
                      <span className="text-blue-600 dark:text-blue-400">
                        {stat.average_response_time.toFixed(2)}ms
                      </span>
                    </div>
                    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5 mt-2">
                      <motion.div
                        className="bg-green-600 h-2.5 rounded-full"
                        initial={{ width: 0 }}
                        animate={{ width: `${(stat.successful_uses / stat.total_uses) * 100}%` }}
                        transition={{ duration: 0.5, ease: "easeOut" }}
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  );
} 