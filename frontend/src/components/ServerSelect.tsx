import { Fragment, useEffect, useState } from 'react'
import { Listbox, Transition } from '@headlessui/react'
import { CheckIcon, ChevronUpDownIcon, ServerIcon } from '@heroicons/react/24/outline'
import { useSession } from 'next-auth/react'
import Image from 'next/image'
import { useThemeStore } from '@/lib/store'
import { getBotServers, type BotGuild } from '@/lib/api'
import { useQuery } from '@tanstack/react-query'

interface Guild {
  id: string
  name: string
  icon: string | null
  permissions: string
  owner: boolean
}

declare module "next-auth" {
  interface Session {
    accessToken?: string
  }
}

export default function ServerSelect() {
  const { data: session } = useSession()
  const [guilds, setGuilds] = useState<Guild[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [retryAfter, setRetryAfter] = useState(0)
  const isDarkMode = useThemeStore((state) => state.isDarkMode)
  const selectedServer = useThemeStore((state) => state.selectedServer)
  const setSelectedServer = useThemeStore((state) => state.setSelectedServer)

  const { data: botServers, isLoading: isBotServersLoading } = useQuery({
    queryKey: ['botServers'],
    queryFn: getBotServers,
    enabled: !!session,
    gcTime: 5 * 60 * 1000,
    staleTime: 30000,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    retry: 3
  })

  useEffect(() => {
    const fetchGuilds = async () => {
      if (session?.accessToken && botServers && !retryAfter) {
        try {
          setIsLoading(true)
          const response = await fetch('https://discord.com/api/users/@me/guilds', {
            headers: {
              Authorization: `Bearer ${session.accessToken}`,
            },
          })

          if (response.status === 429) {
            const data = await response.json()
            setRetryAfter(data.retry_after * 1000)
            setTimeout(() => setRetryAfter(0), data.retry_after * 1000)
            return
          }

          if (!response.ok) {
            console.error('Failed to fetch user guilds:', await response.text())
            return
          }

          const data: Guild[] = await response.json()
          
          const botServerIds = new Set(botServers.map(server => server.id))
          const managedGuilds = data.filter(guild => {
            const permissions = BigInt(guild.permissions)
            const hasPermission = guild.owner || (permissions & BigInt(0x20)) === BigInt(0x20)
            const isBotPresent = botServerIds.has(guild.id)
            return hasPermission && isBotPresent
          })
          
          setGuilds(managedGuilds)

          // If we have guilds but no selection, select the first one
          if (managedGuilds.length > 0 && !selectedServer) {
            setSelectedServer(managedGuilds[0])
          }
        } catch (error) {
          console.error('Failed to fetch guilds:', error)
        } finally {
          setIsLoading(false)
        }
      }
    }

    fetchGuilds()
  }, [session?.accessToken, botServers, retryAfter, selectedServer, setSelectedServer])

  if (!session) return null

  const isLoadingAny = isLoading || isBotServersLoading

  return (
    <div className="space-y-4">
      <Listbox value={selectedServer} onChange={setSelectedServer}>
        <div className="relative">
          <Listbox.Button className={`
            relative w-full cursor-default rounded-lg py-3 pl-3 pr-10 text-left
            shadow-md focus:outline-none focus-visible:border-indigo-500
            focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-opacity-75
            focus-visible:ring-offset-2 focus-visible:ring-offset-indigo-300
            transition-all duration-200 ease-in-out transform hover:scale-[1.02]
            ${isDarkMode ? 'bg-gray-700 hover:bg-gray-600' : 'bg-white hover:bg-gray-50'}
            ${isLoadingAny ? 'animate-pulse' : ''}
          `}>
            {isLoadingAny ? (
              <div className="flex items-center">
                <div className="flex space-x-4 items-center w-full">
                  <div className="rounded-full bg-gray-400 h-6 w-6 animate-pulse"></div>
                  <div className="h-4 bg-gray-400 rounded w-3/4 animate-pulse"></div>
                </div>
              </div>
            ) : selectedServer ? (
              <div className="flex items-center">
                {selectedServer.icon ? (
                  <Image
                    src={`https://cdn.discordapp.com/icons/${selectedServer.id}/${selectedServer.icon}.png`}
                    alt={selectedServer.name}
                    width={24}
                    height={24}
                    className="mr-2 h-6 w-6 rounded-full transition-transform duration-200 group-hover:scale-110"
                    loading="eager"
                  />
                ) : (
                  <div className={`mr-2 h-6 w-6 rounded-full flex items-center justify-center transition-colors duration-200 ${isDarkMode ? 'bg-gray-600' : 'bg-gray-200'}`}>
                    <ServerIcon className="h-4 w-4" />
                  </div>
                )}
                <span className="block truncate">{selectedServer.name}</span>
              </div>
            ) : (
              <span className={`block truncate ${isDarkMode ? 'text-gray-300' : 'text-gray-500'}`}>
                Select a server
              </span>
            )}
            <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
              <ChevronUpDownIcon
                className={`h-5 w-5 transition-transform duration-200 ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}
                aria-hidden="true"
              />
            </span>
          </Listbox.Button>

          <Transition
            as={Fragment}
            leave="transition ease-in duration-100"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
            enter="transition ease-out duration-100"
            enterFrom="opacity-0"
            enterTo="opacity-100"
          >
            <Listbox.Options className={`
              absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md py-1 text-base
              shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none sm:text-sm
              transform transition-all duration-200
              ${isDarkMode ? 'bg-gray-700' : 'bg-white'}
            `}>
              {guilds.map((guild) => (
                <Listbox.Option
                  key={guild.id}
                  className={({ active }) => `
                    relative cursor-default select-none py-2 pl-10 pr-4
                    transition-all duration-200 ease-in-out
                    ${active
                      ? isDarkMode
                        ? 'bg-gray-600 text-white'
                        : 'bg-indigo-100 text-indigo-900'
                      : isDarkMode
                        ? 'text-gray-300'
                        : 'text-gray-900'
                    }
                  `}
                  value={guild}
                >
                  {({ selected, active }) => (
                    <>
                      <div className="flex items-center">
                        {guild.icon ? (
                          <Image
                            src={`https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png`}
                            alt={guild.name}
                            width={24}
                            height={24}
                            className={`
                              mr-2 h-6 w-6 rounded-full
                              transition-all duration-200
                              ${active ? 'scale-110' : ''}
                            `}
                            loading="eager"
                          />
                        ) : (
                          <div className={`
                            mr-2 h-6 w-6 rounded-full flex items-center justify-center
                            transition-all duration-200
                            ${isDarkMode ? 'bg-gray-500' : 'bg-gray-200'}
                            ${active ? 'scale-110' : ''}
                          `}>
                            <ServerIcon className="h-4 w-4" />
                          </div>
                        )}
                        <span className={`
                          block truncate transition-all duration-200
                          ${selected ? 'font-medium' : 'font-normal'}
                          ${active ? 'scale-105' : ''}
                        `}>
                          {guild.name}
                        </span>
                      </div>
                      {selected ? (
                        <span className={`
                          absolute inset-y-0 left-0 flex items-center pl-3
                          transition-all duration-200
                          ${isDarkMode ? 'text-indigo-300' : 'text-indigo-600'}
                        `}>
                          <CheckIcon className="h-5 w-5" aria-hidden="true" />
                        </span>
                      ) : null}
                    </>
                  )}
                </Listbox.Option>
              ))}
            </Listbox.Options>
          </Transition>
        </div>
      </Listbox>

      {selectedServer && (
        <div className={`
          mt-4 rounded-lg p-4
          transform transition-all duration-300 ease-in-out
          hover:scale-[1.02]
          ${isDarkMode ? 'bg-gray-700' : 'bg-gray-50'}
        `}>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className={`text-sm font-medium ${isDarkMode ? 'text-gray-300' : 'text-gray-600'}`}>Server ID</span>
              <span className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>{selectedServer.id}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className={`text-sm font-medium ${isDarkMode ? 'text-gray-300' : 'text-gray-600'}`}>Role</span>
              <span className={`text-sm ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}>
                {selectedServer.owner ? 'Owner' : 'Administrator'}
              </span>
            </div>
            <div className="flex items-center space-x-2">
              {selectedServer.owner && (
                <span className={`
                  inline-flex items-center rounded-full px-2 py-1 text-xs font-medium
                  transition-all duration-200 hover:scale-105
                  ${isDarkMode ? 'bg-indigo-900 text-indigo-300' : 'bg-indigo-100 text-indigo-700'}
                `}>
                  Owner
                </span>
              )}
              <span className={`
                inline-flex items-center rounded-full px-2 py-1 text-xs font-medium
                transition-all duration-200 hover:scale-105
                ${isDarkMode ? 'bg-green-900 text-green-300' : 'bg-green-100 text-green-700'}
              `}>
                Manage Server
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
} 