import { useRouter } from 'next/router'
import { useThemeStore } from '@/lib/store'
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline'

export default function AuthError() {
  const router = useRouter()
  const { error } = router.query
  const isDarkMode = useThemeStore((state) => state.isDarkMode)

  return (
    <div className="min-h-screen flex flex-col justify-center items-center px-4 sm:px-6 lg:px-8">
      <div className={`
        max-w-md w-full space-y-8 p-8 rounded-lg shadow-lg
        ${isDarkMode ? 'bg-gray-800' : 'bg-white'}
      `}>
        <div>
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
            <ExclamationTriangleIcon className="h-8 w-8 text-red-600" aria-hidden="true" />
          </div>
          <h2 className={`
            mt-6 text-center text-3xl font-bold tracking-tight
            ${isDarkMode ? 'text-white' : 'text-gray-900'}
          `}>
            Authentication Error
          </h2>
          <p className={`
            mt-2 text-center text-sm
            ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}
          `}>
            {error === 'AccessDenied'
              ? 'You do not have permission to access this resource.'
              : error === 'Configuration'
              ? 'There is a problem with the server configuration.'
              : error === 'Verification'
              ? 'The verification token has expired or is invalid.'
              : 'An error occurred during authentication.'}
          </p>
        </div>
        <div className="mt-8">
          <button
            onClick={() => router.push('/auth/signin')}
            className={`
              group relative flex w-full justify-center rounded-md px-3 py-2 text-sm font-semibold
              focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2
              transition-all duration-200 ease-in-out
              ${isDarkMode
                ? 'bg-indigo-600 text-white hover:bg-indigo-500 focus-visible:outline-indigo-600'
                : 'bg-indigo-600 text-white hover:bg-indigo-500 focus-visible:outline-indigo-600'
              }
            `}
          >
            Try Again
          </button>
        </div>
      </div>
    </div>
  )
} 