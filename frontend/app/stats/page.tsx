'use client';

import { useEffect, useState } from 'react';
import { useServerStore } from '../../stores/serverStore';
import { motion } from 'framer-motion';
import { BarChart as BarChartIcon, Users, Shield, Clock } from 'lucide-react';

interface Stats {
  totalCases: number;
  activeModerators: number;
  averageResponseTime: string;
  casesPerDay: number;
}

export default function StatsPage() {
  const { selectedServer } = useServerStore();
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      if (!selectedServer) return;
      try {
        const response = await fetch(`/api/stats/${selectedServer.id}`, {
          credentials: 'include',
        });
        if (!response.ok) throw new Error('Failed to fetch stats');
        const data = await response.json();
        setStats(data);
      } catch (error) {
        console.error('Error fetching stats:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
  }, [selectedServer]);

  if (!selectedServer) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-4rem)] text-center px-4">
        <h1 className="text-2xl font-bold mb-4">Please Select a Server</h1>
        <p className="text-gray-600 dark:text-gray-400">
          Choose a server from the dropdown in the top left corner to view statistics.
        </p>
      </div>
    );
  }

  const statCards = [
    {
      title: 'Total Cases',
      value: stats?.totalCases || 0,
      icon: BarChartIcon,
      color: 'bg-blue-500',
    },
    {
      title: 'Active Moderators',
      value: stats?.activeModerators || 0,
      icon: Shield,
      color: 'bg-green-500',
    },
    {
      title: 'Average Response',
      value: stats?.averageResponseTime || '0m',
      icon: Clock,
      color: 'bg-purple-500',
    },
    {
      title: 'Cases Per Day',
      value: stats?.casesPerDay || 0,
      icon: Users,
      color: 'bg-orange-500',
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <h1 className="text-2xl font-bold">Statistics for {selectedServer.name}</h1>
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          Download Report
        </motion.button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="animate-pulse bg-gray-100 dark:bg-gray-800 rounded-lg p-6 h-32"
            />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {statCards.map((stat, index) => {
            const Icon = stat.icon;
            return (
              <motion.div
                key={stat.title}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1 }}
                className="bg-white dark:bg-gray-800 rounded-lg p-6 shadow-sm"
              >
                <div className="flex items-center space-x-4">
                  <div className={`p-3 rounded-lg ${stat.color} bg-opacity-10`}>
                    <Icon className={`w-6 h-6 ${stat.color.replace('bg-', 'text-')}`} />
                  </div>
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">{stat.title}</p>
                    <p className="text-2xl font-semibold">{stat.value}</p>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

      <div className="mt-8 bg-white dark:bg-gray-800 rounded-lg p-6 shadow-sm">
        <h2 className="text-lg font-semibold mb-4">Recent Activity</h2>
        <div className="h-64 flex items-center justify-center text-gray-500 dark:text-gray-400">
          Chart will be implemented here
        </div>
      </div>
    </div>
  );
} 