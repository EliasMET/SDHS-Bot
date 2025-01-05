import { useSession, signIn, signOut } from 'next-auth/react';
import { SunIcon, MoonIcon } from '@heroicons/react/24/outline';
import { useThemeStore } from '@/lib/store';
import Image from 'next/image';
import { motion } from 'framer-motion';

const defaultLogo = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwYXRoIGQ9Ik0zIDlsMTgtOSAxOCA5TTMgOWwxOCA2IDE4LTYiPjwvcGF0aD48L3N2Zz4=';

export default function Navbar() {
  const { data: session } = useSession();
  const isDarkMode = useThemeStore((state) => state.isDarkMode);
  const toggleDarkMode = useThemeStore((state) => state.toggleDarkMode);

  return (
    <nav className={`fixed top-0 left-0 right-0 z-50 border-b ${
      isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'
    }`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <motion.div
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <Image
                className="h-8 w-auto"
                src={defaultLogo}
                alt="SDHS Bot"
                width={32}
                height={32}
                priority
              />
            </motion.div>
          </div>

          <div className="flex items-center gap-4">
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={toggleDarkMode}
              className={`rounded-lg p-2 transition-colors ${
                isDarkMode 
                  ? 'text-yellow-500 hover:bg-gray-700' 
                  : 'text-gray-500 hover:bg-gray-100'
              }`}
            >
              {isDarkMode ? (
                <SunIcon className="h-5 w-5" />
              ) : (
                <MoonIcon className="h-5 w-5" />
              )}
            </motion.button>

            {session ? (
              <div className="flex items-center gap-3">
                <motion.div
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  className="relative"
                >
                  <Image
                    className="h-8 w-8 rounded-full"
                    src={session.user?.image || defaultLogo}
                    alt=""
                    width={32}
                    height={32}
                    priority
                  />
                  <span className="absolute bottom-0 right-0 block h-2 w-2 rounded-full bg-green-400 ring-2 ring-white dark:ring-gray-800" />
                </motion.div>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => signOut()}
                  className={`text-sm font-medium ${
                    isDarkMode ? 'text-gray-300 hover:text-white' : 'text-gray-700 hover:text-gray-900'
                  }`}
                >
                  Sign out
                </motion.button>
              </div>
            ) : (
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => signIn('discord')}
                className="text-discord-blurple hover:text-discord-blurple-dark font-medium"
              >
                Sign in with Discord
              </motion.button>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
} 