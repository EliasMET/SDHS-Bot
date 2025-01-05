'use client';

import { useSession, signIn, signOut } from 'next-auth/react';
import { ServerSelector } from './ServerSelector';
import { useTheme } from 'next-themes';
import { Sun, Moon, SignOut, SignIn, DiscordLogo } from '@phosphor-icons/react';
import Image from 'next/image';
import { useState, useEffect } from 'react';

export function Navbar() {
  const { data: session } = useSession();
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return null;
  }

  return (
    <nav className="sticky top-0 z-50 w-full bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
      <div className="px-4 py-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <div className="w-8 h-8 flex items-center justify-center rounded-full bg-indigo-100 dark:bg-indigo-900">
                <DiscordLogo
                  className="w-5 h-5 text-indigo-600 dark:text-indigo-400"
                  weight="fill"
                />
              </div>
              <span className="font-semibold text-xl">SDHS Bot</span>
            </div>
            {session && <ServerSelector />}
          </div>

          <div className="flex items-center space-x-4">
            <button
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              aria-label="Toggle theme"
            >
              {theme === 'dark' ? (
                <Sun className="w-5 h-5" weight="fill" />
              ) : (
                <Moon className="w-5 h-5" weight="fill" />
              )}
            </button>

            {session ? (
              <div className="flex items-center space-x-4">
                <div className="flex items-center space-x-2">
                  {session.user?.image && (
                    <Image
                      src={session.user.image}
                      alt={session.user.name || 'User avatar'}
                      width={32}
                      height={32}
                      className="rounded-full"
                    />
                  )}
                  <span className="font-medium">{session.user?.name}</span>
                </div>
                <button
                  onClick={() => signOut()}
                  className="flex items-center space-x-1 px-3 py-2 rounded-lg bg-red-500 hover:bg-red-600 text-white transition-colors"
                >
                  <SignOut className="w-5 h-5" weight="fill" />
                  <span>Sign out</span>
                </button>
              </div>
            ) : (
              <button
                onClick={() => signIn('discord')}
                className="flex items-center space-x-1 px-3 py-2 rounded-lg bg-indigo-500 hover:bg-indigo-600 text-white transition-colors"
              >
                <SignIn className="w-5 h-5" weight="fill" />
                <span>Sign in</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
} 