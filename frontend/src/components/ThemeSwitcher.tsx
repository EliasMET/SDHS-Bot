import { useEffect, useState } from 'react';
import { SunIcon, MoonIcon, ComputerDesktopIcon } from '@heroicons/react/24/outline';
import { useThemeStore } from '@/lib/store';

export default function ThemeSwitcher(): JSX.Element {
  const [mounted, setMounted] = useState<boolean>(false);
  const { theme, setTheme } = useThemeStore();

  // Ensure component is mounted before rendering to avoid hydration mismatch
  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return null;
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => setTheme('light')}
        className={`p-2 rounded-lg transition-colors ${
          theme === 'light'
            ? 'bg-gray-200 text-gray-900 dark:bg-gray-700 dark:text-white'
            : 'text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white'
        }`}
        title="Light mode"
        type="button"
      >
        <SunIcon className="h-5 w-5" />
      </button>
      <button
        onClick={() => setTheme('dark')}
        className={`p-2 rounded-lg transition-colors ${
          theme === 'dark'
            ? 'bg-gray-200 text-gray-900 dark:bg-gray-700 dark:text-white'
            : 'text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white'
        }`}
        title="Dark mode"
        type="button"
      >
        <MoonIcon className="h-5 w-5" />
      </button>
      <button
        onClick={() => setTheme('system')}
        className={`p-2 rounded-lg transition-colors ${
          theme === 'system'
            ? 'bg-gray-200 text-gray-900 dark:bg-gray-700 dark:text-white'
            : 'text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white'
        }`}
        title="System theme"
        type="button"
      >
        <ComputerDesktopIcon className="h-5 w-5" />
      </button>
    </div>
  );
} 