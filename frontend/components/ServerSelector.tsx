import { Fragment, useEffect, useState, useCallback } from 'react';
import { Listbox, Transition } from '@headlessui/react';
import { CheckIcon, ChevronUpDownIcon } from '@heroicons/react/24/outline';
import { useSession } from 'next-auth/react';
import { useQuery } from '@tanstack/react-query';
import { getBotServers, Guild } from '@/lib/api';
import { useServerStore } from '@/stores/serverStore';
import Image from 'next/image';

export function ServerSelector() {
  const { data: session, status } = useSession();
  const selectedServer = useServerStore((state) => state.selectedServer);
  const setSelectedServer = useServerStore((state) => state.setSelectedServer);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const fetchServers = useCallback(async () => {
    if (!session?.accessToken) {
      return [];
    }
    return getBotServers();
  }, [session?.accessToken]);

  const { data: servers, isLoading, error } = useQuery({
    queryKey: ['servers', session?.accessToken],
    queryFn: fetchServers,
    enabled: mounted && status === 'authenticated',
    staleTime: 1000 * 60 * 5, // 5 minutes
    gcTime: 1000 * 60 * 60, // 1 hour
    refetchOnWindowFocus: false,
    retry: 1,
  });

  useEffect(() => {
    if (servers?.length && !selectedServer) {
      setSelectedServer(servers[0]);
    }
  }, [servers, selectedServer, setSelectedServer]);

  if (!mounted || status !== 'authenticated') return null;

  return (
    <div className="w-72">
      <Listbox value={selectedServer} onChange={setSelectedServer}>
        <div className="relative mt-1">
          <Listbox.Button className="relative w-full cursor-default rounded-lg bg-white dark:bg-gray-800 py-2 pl-3 pr-10 text-left shadow-md focus:outline-none focus-visible:border-indigo-500 focus-visible:ring-2 focus-visible:ring-white/75 focus-visible:ring-offset-2 focus-visible:ring-offset-indigo-300 sm:text-sm">
            {isLoading ? (
              <span className="block truncate text-gray-500">Loading servers...</span>
            ) : error ? (
              <span className="block truncate text-red-500">Error loading servers</span>
            ) : selectedServer ? (
              <div className="flex items-center space-x-2">
                {selectedServer.icon ? (
                  <Image
                    src={`https://cdn.discordapp.com/icons/${selectedServer.id}/${selectedServer.icon}.png`}
                    alt={selectedServer.name}
                    width={24}
                    height={24}
                    className="rounded-full"
                    unoptimized
                  />
                ) : (
                  <div className="w-6 h-6 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center">
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {selectedServer.name.charAt(0)}
                    </span>
                  </div>
                )}
                <span className="block truncate">{selectedServer.name}</span>
              </div>
            ) : (
              <span className="block truncate text-gray-500">Select a server</span>
            )}
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
              {servers?.map((server) => (
                <Listbox.Option
                  key={server.id}
                  className={({ active }) =>
                    `relative cursor-default select-none py-2 pl-10 pr-4 ${
                      active
                        ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-900 dark:text-indigo-100'
                        : 'text-gray-900 dark:text-gray-100'
                    }`
                  }
                  value={server}
                >
                  {({ selected }) => (
                    <>
                      <div className="flex items-center space-x-2">
                        {server.icon ? (
                          <Image
                            src={`https://cdn.discordapp.com/icons/${server.id}/${server.icon}.png`}
                            alt={server.name}
                            width={24}
                            height={24}
                            className="rounded-full"
                            unoptimized
                          />
                        ) : (
                          <div className="w-6 h-6 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center">
                            <span className="text-xs text-gray-500 dark:text-gray-400">
                              {server.name.charAt(0)}
                            </span>
                          </div>
                        )}
                        <span className={`block truncate ${selected ? 'font-medium' : 'font-normal'}`}>
                          {server.name}
                        </span>
                      </div>
                      {selected && (
                        <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-indigo-600 dark:text-indigo-400">
                          <CheckIcon className="h-5 w-5" aria-hidden="true" />
                        </span>
                      )}
                    </>
                  )}
                </Listbox.Option>
              ))}
            </Listbox.Options>
          </Transition>
        </div>
      </Listbox>
    </div>
  );
} 