import { useSession } from 'next-auth/react'
import { useQuery } from '@tanstack/react-query'
import { getServerCases } from '@/lib/api'
import { format } from 'date-fns'
import { useThemeStore } from '@/lib/store'
import { ServerIcon, ShieldExclamationIcon } from '@heroicons/react/24/outline'
import { Transition } from '@headlessui/react'
import ServerSelect from '@/components/ServerSelect'

export default function Cases() {
  const { data: session } = useSession()
  const isDarkMode = useThemeStore((state) => state.isDarkMode)
  const selectedServer = useThemeStore((state) => state.selectedServer)

  const { data: cases, isLoading, error } = useQuery({
    queryKey: ['cases', selectedServer?.id],
    queryFn: () => getServerCases(selectedServer!.id),
    enabled: !!selectedServer && !!session,
    retry: 3,
    refetchOnWindowFocus: true,
    staleTime: 30000
  })

  if (!session) {
    return (
      <div className="text-center">
        <h1 className={`text-4xl font-bold tracking-tight sm:text-6xl mb-4 ${
          isDarkMode ? 'text-white' : 'text-gray-900'
        }`}>
          Access Denied
        </h1>
        <p className={`text-lg leading-8 ${isDarkMode ? 'text-gray-300' : 'text-gray-600'}`}>
          Please sign in to view cases.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div className="md:flex md:items-center md:justify-between">
        <div className="min-w-0 flex-1">
          <h2 className={`text-2xl font-bold leading-7 sm:truncate sm:text-3xl sm:tracking-tight ${
            isDarkMode ? 'text-white' : 'text-gray-900'
          }`}>
            Cases
          </h2>
        </div>
      </div>

      <div className="max-w-2xl">
        <ServerSelect />
      </div>
      
      <div className="mt-8">
        {isLoading ? (
          <div className="animate-pulse space-y-4">
            {[...Array(5)].map((_, i) => (
              <div 
                key={i} 
                className={`rounded-lg p-6 ${isDarkMode ? 'bg-gray-800' : 'bg-gray-100'}`}
                style={{ animationDelay: `${i * 150}ms` }}
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center space-x-4">
                    <div className="h-8 w-8 rounded-full bg-gray-400"></div>
                    <div className="h-4 w-32 bg-gray-400 rounded"></div>
                  </div>
                  <div className="h-4 w-24 bg-gray-400 rounded"></div>
                </div>
                <div className="space-y-3">
                  <div className="h-4 bg-gray-400 rounded w-3/4"></div>
                  <div className="h-4 bg-gray-400 rounded w-1/2"></div>
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className={`
            text-center p-12 rounded-lg border-2 border-dashed
            ${isDarkMode 
              ? 'text-red-400 border-red-700' 
              : 'text-red-600 border-red-200'
            }
          `}>
            <ShieldExclamationIcon className="mx-auto h-12 w-12 mb-4" />
            <p className="text-lg font-medium mb-2">Error Loading Cases</p>
            <p className="text-sm">
              {error instanceof Error ? error.message : 'Failed to load cases. Please try again.'}
            </p>
          </div>
        ) : cases && cases.length > 0 ? (
          <div className="space-y-4">
            {cases.map((case_, index) => (
              <Transition
                key={case_.case_id}
                show={true}
                appear={true}
                enter="transform transition duration-500 ease-out"
                enterFrom="opacity-0 translate-y-4"
                enterTo="opacity-100 translate-y-0"
                style={{ transitionDelay: `${index * 100}ms` }}
              >
                <div
                  className={`
                    rounded-lg p-6 shadow-sm
                    transform transition-all duration-200 ease-in-out
                    hover:scale-[1.01] hover:shadow-md
                    ${isDarkMode ? 'bg-gray-800 hover:bg-gray-750' : 'bg-white hover:bg-gray-50'}
                  `}
                >
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center space-x-3">
                      <div className={`
                        p-2 rounded-full
                        ${case_.action_type === 'warn'
                          ? 'bg-yellow-100 text-yellow-700'
                          : case_.action_type === 'mute'
                          ? 'bg-blue-100 text-blue-700'
                          : case_.action_type === 'kick'
                          ? 'bg-orange-100 text-orange-700'
                          : 'bg-red-100 text-red-700'
                        }
                      `}>
                        <ShieldExclamationIcon className="h-5 w-5" />
                      </div>
                      <div>
                        <span className={`font-medium ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                          Case #{case_.case_id}
                        </span>
                        <span className={`
                          ml-2 px-2 py-1 rounded-full text-xs font-medium
                          ${case_.action_type === 'warn'
                            ? 'bg-yellow-100 text-yellow-800'
                            : case_.action_type === 'mute'
                            ? 'bg-blue-100 text-blue-800'
                            : case_.action_type === 'kick'
                            ? 'bg-orange-100 text-orange-800'
                            : 'bg-red-100 text-red-800'
                          }
                        `}>
                          {case_.action_type.toUpperCase()}
                        </span>
                      </div>
                    </div>
                    <span className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                      {format(new Date(case_.timestamp), 'PPpp')}
                    </span>
                  </div>
                  <div className="mt-2">
                    <p className={`text-sm ${isDarkMode ? 'text-gray-300' : 'text-gray-600'}`}>
                      {case_.reason}
                    </p>
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
                    <div className={`${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                      <span className="font-medium">User:</span> {case_.user_id}
                    </div>
                    <div className={`${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                      <span className="font-medium">Moderator:</span> {case_.moderator_id}
                    </div>
                  </div>
                </div>
              </Transition>
            ))}
          </div>
        ) : (
          <div className={`
            text-center p-12 rounded-lg border-2 border-dashed
            ${isDarkMode 
              ? 'text-gray-400 border-gray-700' 
              : 'text-gray-600 border-gray-200'
            }
          `}>
            <ServerIcon className="mx-auto h-12 w-12 mb-4" />
            <p className="text-lg font-medium mb-2">
              {selectedServer ? 'No cases found' : 'Select a server to view cases'}
            </p>
            <p className="text-sm">
              {selectedServer 
                ? 'There are no moderation cases for this server yet.'
                : 'Choose a server from the dropdown above to view its moderation cases.'
              }
            </p>
          </div>
        )}
      </div>
    </div>
  )
} 