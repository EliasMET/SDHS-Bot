import { useSession } from 'next-auth/react';
import { useThemeStore } from '@/lib/store';
import TryoutSettings from '@/components/TryoutSettings';

export default function Tryouts() {
  const { data: session } = useSession();
  const theme = useThemeStore((state) => state.theme);
  const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  if (!session) {
    return (
      <div className="text-center">
        <h1 className={`text-4xl font-bold tracking-tight sm:text-6xl mb-4 ${
          isDark ? 'text-white' : 'text-gray-900'
        }`}>
          Access Denied
        </h1>
        <p className={`text-lg leading-8 ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
          Please sign in to access tryouts.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="md:flex md:items-center md:justify-between">
        <div className="min-w-0 flex-1">
          <h2 className={`text-2xl font-bold leading-7 sm:truncate sm:text-3xl sm:tracking-tight ${
            isDark ? 'text-white' : 'text-gray-900'
          }`}>
            Tryouts
          </h2>
        </div>
      </div>
      
      <div className="mt-8">
        <TryoutSettings />
      </div>
    </div>
  );
} 