import { useSession } from 'next-auth/react';
import { useThemeStore } from '@/lib/store';
import { useEffect } from 'react';
import Navbar from './Navbar';
import Sidebar from './Sidebar';
import ServerSelect from './ServerSelect';
import { motion, AnimatePresence } from 'framer-motion';
import type { ReactNode } from 'react';

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const { data: session } = useSession();
  const isDarkMode = useThemeStore((state) => state.isDarkMode);
  const selectedServer = useThemeStore((state) => state.selectedServer);

  // Apply dark mode class to html element
  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDarkMode]);

  return (
    <div className={`min-h-screen ${isDarkMode ? 'dark bg-gray-900' : 'bg-gray-50'}`}>
      <Navbar />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 p-6 ml-64 mt-16">
          {session && (
            <div className="mb-6 max-w-xl">
              <ServerSelect />
            </div>
          )}
          <AnimatePresence mode="wait">
            <motion.div
              key={selectedServer?.id || 'no-server'}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.2 }}
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
} 