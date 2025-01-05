'use client';

import { useEffect, useState } from 'react';
import { useServerStore } from '../../stores/serverStore';
import { motion } from 'framer-motion';

interface Case {
  id: string;
  userId: string;
  moderatorId: string;
  type: string;
  reason: string;
  createdAt: string;
  duration?: string;
}

export default function CasesPage() {
  const { selectedServer } = useServerStore();
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchCases = async () => {
      if (!selectedServer) return;
      try {
        const response = await fetch(`/api/cases/${selectedServer.id}`, {
          credentials: 'include',
        });
        if (!response.ok) throw new Error('Failed to fetch cases');
        const data = await response.json();
        setCases(data);
      } catch (error) {
        console.error('Error fetching cases:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchCases();
  }, [selectedServer]);

  if (!selectedServer) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-4rem)] text-center px-4">
        <h1 className="text-2xl font-bold mb-4">Please Select a Server</h1>
        <p className="text-gray-600 dark:text-gray-400">
          Choose a server from the dropdown in the top left corner to view cases.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <h1 className="text-2xl font-bold">Cases for {selectedServer.name}</h1>
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          Export Cases
        </motion.button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div
              key={i}
              className="animate-pulse bg-gray-100 dark:bg-gray-800 rounded-lg p-6 h-32"
            />
          ))}
        </div>
      ) : cases.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-600 dark:text-gray-400">No cases found.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {cases.map((case_) => (
            <motion.div
              key={case_.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-white dark:bg-gray-800 rounded-lg p-6 shadow-sm"
            >
              <div className="flex justify-between items-start mb-4">
                <span className="px-2 py-1 text-sm rounded-full bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200">
                  {case_.type}
                </span>
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  {new Date(case_.createdAt).toLocaleDateString()}
                </span>
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-300 mb-4">
                {case_.reason}
              </p>
              {case_.duration && (
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Duration: {case_.duration}
                </p>
              )}
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
} 