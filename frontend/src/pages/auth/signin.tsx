import { signIn } from 'next-auth/react'
import { useThemeStore } from '@/lib/store'
import Image from 'next/image'

export default function SignIn() {
  const isDarkMode = useThemeStore((state) => state.isDarkMode)

  return (
    <div className="min-h-screen flex flex-col justify-center items-center px-4 sm:px-6 lg:px-8">
      <div className={`
        max-w-md w-full space-y-8 p-8 rounded-lg shadow-lg
        ${isDarkMode ? 'bg-gray-800' : 'bg-white'}
      `}>
        <div>
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100">
            <Image
              src="/discord-mark-blue.svg"
              alt="Discord Logo"
              width={32}
              height={32}
              priority
            />
          </div>
          <h2 className={`
            mt-6 text-center text-3xl font-bold tracking-tight
            ${isDarkMode ? 'text-white' : 'text-gray-900'}
          `}>
            Sign in to your account
          </h2>
          <p className={`
            mt-2 text-center text-sm
            ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}
          `}>
            Use your Discord account to access the dashboard
          </p>
        </div>
        <div className="mt-8">
          <button
            onClick={() => signIn('discord', { callbackUrl: '/' })}
            className={`
              group relative flex w-full justify-center rounded-md px-3 py-2 text-sm font-semibold
              focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2
              transition-all duration-200 ease-in-out
              ${isDarkMode
                ? 'bg-[#5865F2] text-white hover:bg-[#4752C4] focus-visible:outline-[#5865F2]'
                : 'bg-[#5865F2] text-white hover:bg-[#4752C4] focus-visible:outline-[#5865F2]'
              }
            `}
          >
            <Image
              src="/discord-mark-white.svg"
              alt="Discord Logo"
              width={20}
              height={20}
              className="mr-2"
              priority
            />
            Continue with Discord
          </button>
        </div>
      </div>
    </div>
  )
} 