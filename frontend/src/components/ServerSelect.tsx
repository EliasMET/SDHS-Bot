import { Fragment, useEffect, useState, useCallback } from 'react'
import { Listbox, Transition } from '@headlessui/react'
import { CheckIcon, ChevronUpDownIcon, ServerIcon } from '@heroicons/react/24/outline'
import { useSession } from 'next-auth/react'
import { useQuery } from '@tanstack/react-query'
import { getBotServers } from '@/lib/api'
import { useThemeStore } from '@/lib/store'
import Image from 'next/image'

interface Guild {
  id: string
  name: string
  icon: string | null
  permissions: string
}

const DISCORD_API_CACHE_TIME = 5 * 60 * 1000; // 5 minutes
const DISCORD_API_STALE_TIME = 60 * 1000; // 1 minute

export default function ServerSelect() {
  const { data: session } = useSession()
  const [guilds, setGuilds] = useState<Guild[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const selectedServer = useThemeStore((state) => state.selectedServer)
  const setSelectedServer = useThemeStore((state) => state.setSelectedServer)
  const [lastFetch, setLastFetch] = useState<number>(0)
  const FETCH_COOLDOWN = 10000 // 10 seconds cooldown

  const { data: botServers, isLoading: isBotServersLoading } = useQuery({
    queryKey: ['botServers'],
    queryFn: getBotServers,
    staleTime: DISCORD_API_STALE_TIME,
    cacheTime: DISCORD_API_CACHE_TIME,
  })

  const fetchGuilds = useCallback(async () => {
    const now = Date.now()
    if (now - lastFetch < FETCH_COOLDOWN) {
      return
    }

    try {
      setIsLoading(true)
      setLastFetch(now)
      const response = await fetch('https://discord.com/api/users/@me/guilds', {
        headers: {
          Authorization: `Bearer ${session?.accessToken}`,
        },
      })

      if (response.status === 429) {
        const retryAfter = parseInt(response.headers.get('Retry-After') || '5')
        await new Promise(resolve => setTimeout(resolve, retryAfter * 1000))
        return fetchGuilds()
      }

      if (!response.ok) {
        throw new Error('Failed to fetch guilds')
      }

      const allGuilds = await response.json()
      // Filter for guilds where user has MANAGE_GUILD permission
      const managedGuilds = allGuilds.filter((guild: Guild) => 
        (BigInt(guild.permissions) & BigInt(0x20)) === BigInt(0x20)
      )

      // Filter for guilds where the bot is present
      if (botServers) {
        const botServerIds = new Set(botServers.map(server => server.id))
        const availableGuilds = managedGuilds.filter((guild: Guild) => 
          botServerIds.has(guild.id)
        )
        setGuilds(availableGuilds)

        // Auto-select first server if none selected
        if (availableGuilds.length > 0 && !selectedServer) {
          setSelectedServer(availableGuilds[0])
        }
      }
    } catch (error) {
      console.error('Error fetching guilds:', error)
      setError('Failed to fetch servers')
    } finally {
      setIsLoading(false)
    }
  }, [session?.accessToken, lastFetch, botServers, selectedServer, setSelectedServer])

  useEffect(() => {
    if (session?.accessToken && botServers) {
      fetchGuilds()
    }
  }, [session?.accessToken, botServers, fetchGuilds])

  if (!session) return null

  return (
    <div className="w-full">
      {selectedServer && (
        <div className="flex items-center gap-2 mb-4">
          {selectedServer.icon && (
            <Image
              src={`https://cdn.discordapp.com/icons/${selectedServer.id}/${selectedServer.icon}.png`}
              alt={selectedServer.name}
              width={32}
              height={32}
              className="rounded-full"
              loading="lazy"
            />
          )}
          <span className="font-medium">{selectedServer.name}</span>
        </div>
      )}

      <Listbox value={selectedServer} onChange={setSelectedServer}>
        <div className="relative mt-1">
          <Listbox.Button className="relative w-full cursor-default rounded-lg bg-white dark:bg-gray-800 py-2 pl-3 pr-10 text-left shadow-md focus:outline-none focus-visible:border-indigo-500 focus-visible:ring-2 focus-visible:ring-white/75 focus-visible:ring-offset-2 focus-visible:ring-offset-orange-300 sm:text-sm">
            <span className="block truncate">
              {isLoading ? (
                'Loading servers...'
              ) : error ? (
                'Error loading servers'
              ) : selectedServer ? (
                selectedServer.name
              ) : (
                'Select a server'
              )}
            </span>
            <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
              <ChevronUpDownIcon
                className="h-5 w-5 text-gray-400"
                aria-hidden="true"
              />
            </span>
          </Listbox.Button>
          <Transition
            as={Fragment}
            leave="transition ease-in duration-100"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <Listbox.Options className="absolute mt-1 max-h-60 w-full overflow-auto rounded-md bg-white dark:bg-gray-800 py-1 text-base shadow-lg ring-1 ring-black/5 focus:outline-none sm:text-sm z-50">
              {guilds.map((guild) => (
                <Listbox.Option
                  key={guild.id}
                  className={({ active }) =>
                    `relative cursor-default select-none py-2 pl-10 pr-4 ${
                      active ? 'bg-indigo-100 dark:bg-indigo-900 text-indigo-900 dark:text-indigo-100' : 'text-gray-900 dark:text-gray-100'
                    }`
                  }
                  value={guild}
                >
                  {({ selected }) => (
                    <>
                      <span
                        className={`block truncate ${
                          selected ? 'font-medium' : 'font-normal'
                        }`}
                      >
                        {guild.name}
                      </span>
                      {selected ? (
                        <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-indigo-600 dark:text-indigo-400">
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
    </div>
  )
} 