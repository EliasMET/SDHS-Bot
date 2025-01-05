'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { getCommandStats } from '@/lib/api';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

interface CommandStat {
  command: string;
  total_uses: number;
  successful_uses: number;
  failed_uses: number;
  unique_users: number;
  average_response_time: number;
}

interface Params {
  id: string;
}

export default function StatisticsPage() {
  const params = useParams<Params>();
  const serverId = params?.id;

  const { data: stats, isLoading } = useQuery({
    queryKey: ['commandStats', serverId],
    queryFn: () => getCommandStats(serverId!),
    enabled: !!serverId,
  });

  if (!serverId) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-6">Invalid Server ID</h1>
        <p className="text-gray-600 dark:text-gray-400">
          Please select a valid server to view statistics.
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="p-6 space-y-4">
        <h1 className="text-2xl font-bold mb-6">Command Statistics</h1>
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-4 w-1/3" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-4 w-full mb-2" />
              <Skeleton className="h-4 w-2/3" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Command Statistics</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {stats?.map((stat: CommandStat) => (
          <Card key={stat.command}>
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
                  <div
                    className="bg-green-600 h-2.5 rounded-full"
                    style={{
                      width: `${(stat.successful_uses / stat.total_uses) * 100}%`,
                    }}
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
} 