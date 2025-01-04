'use client';

import { signIn } from 'next-auth/react';
import Image from 'next/image';
import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';

export default function SignIn() {
  const [mounted, setMounted] = useState(false);
  const { theme } = useTheme();

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return null;
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="max-w-md w-full space-y-8 p-8 bg-white dark:bg-gray-800 rounded-lg shadow-lg">
        <div className="text-center">
          <h2 className="mt-6 text-3xl font-bold text-gray-900 dark:text-white">
            Sign in to SDHS Bot
          </h2>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            Please sign in with your Discord account to continue
          </p>
        </div>
        <div className="mt-8">
          <button
            onClick={() => signIn('discord', { callbackUrl: '/' })}
            className="group relative w-full flex justify-center py-3 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-[#5865F2] hover:bg-[#4752C4] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#5865F2] transition-colors duration-200"
          >
            <span className="absolute left-0 inset-y-0 flex items-center pl-3">
              <Image
                src={theme === 'dark' ? '/discord-mark-white.svg' : '/discord-mark-blue.svg'}
                width={24}
                height={24}
                alt="Discord Logo"
                className={theme === 'dark' ? 'opacity-90' : 'opacity-75'}
              />
            </span>
            Sign in with Discord
          </button>
        </div>
      </div>
    </div>
  );
} 