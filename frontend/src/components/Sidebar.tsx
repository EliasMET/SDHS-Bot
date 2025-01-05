import { useRouter } from 'next/router';
import { useThemeStore } from '@/lib/store';
import { motion } from 'framer-motion';
import {
  HomeIcon,
  UserGroupIcon,
  ShieldCheckIcon,
  ChartBarIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline';

const navigation = [
  { name: 'Dashboard', href: '/', icon: HomeIcon },
  { name: 'Tryouts', href: '/tryouts', icon: UserGroupIcon },
  { name: 'Moderation', href: '/moderation', icon: ShieldCheckIcon },
  { name: 'Cases', href: '/cases', icon: DocumentTextIcon },
  { name: 'Statistics', href: '/stats', icon: ChartBarIcon },
];

export default function Sidebar() {
  const router = useRouter();
  const isDarkMode = useThemeStore((state) => state.isDarkMode);

  return (
    <div className={`fixed inset-y-0 left-0 z-40 w-64 transform transition-transform duration-300 ease-in-out ${
      isDarkMode ? 'bg-gray-800' : 'bg-white'
    } border-r ${isDarkMode ? 'border-gray-700' : 'border-gray-200'} pt-20`}>
      <nav className="flex flex-col h-full px-4">
        <div className="space-y-1">
          {navigation.map((item) => {
            const isActive = router.pathname === item.href;
            return (
              <motion.button
                key={item.name}
                onClick={() => router.push(item.href)}
                className={`
                  relative w-full flex items-center gap-3 px-4 py-3 text-sm font-medium rounded-lg
                  transition-colors duration-200
                  ${isActive
                    ? isDarkMode
                      ? 'bg-gray-700 text-white'
                      : 'bg-gray-100 text-gray-900'
                    : isDarkMode
                      ? 'text-gray-400 hover:text-white hover:bg-gray-700'
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                  }
                `}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <item.icon className="h-5 w-5 shrink-0" aria-hidden="true" />
                <span>{item.name}</span>
                {isActive && (
                  <motion.div
                    className={`absolute inset-y-0 left-0 w-1 rounded-r-lg ${
                      isDarkMode ? 'bg-indigo-500' : 'bg-indigo-600'
                    }`}
                    layoutId="activeTab"
                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                  />
                )}
              </motion.button>
            );
          })}
        </div>
      </nav>
    </div>
  );
} 