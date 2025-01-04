import { Fragment, useState } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import {
  Bars3Icon,
  XMarkIcon,
  HomeIcon,
  UserGroupIcon,
  ShieldCheckIcon,
  ChartBarIcon,
  SunIcon,
  MoonIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline'
import { useSession, signIn, signOut } from 'next-auth/react'
import Image from 'next/image'
import { useRouter } from 'next/router'
import ServerSelect from './ServerSelect'
import { useThemeStore } from '@/lib/store'

const navigation = [
  { name: 'Dashboard', href: '/', icon: HomeIcon },
  { name: 'Tryouts', href: '/tryouts', icon: UserGroupIcon },
  { name: 'Moderation', href: '/moderation', icon: ShieldCheckIcon },
  { name: 'Cases', href: '/cases', icon: DocumentTextIcon },
  { name: 'Statistics', href: '/stats', icon: ChartBarIcon },
]

const defaultLogo = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwYXRoIGQ9Ik0zIDlsMTgtOSAxOCA5TTMgOWwxOCA2IDE4LTYiPjwvcGF0aD48L3N2Zz4='

export default function Layout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { data: session } = useSession()
  const router = useRouter()
  const isDarkMode = useThemeStore((state) => state.isDarkMode)
  const toggleDarkMode = useThemeStore((state) => state.toggleDarkMode)

  const handleNavigation = (href: string) => {
    if (router.pathname !== href) {
      router.push(href)
    }
  }

  return (
    <div className={isDarkMode ? 'dark' : ''}>
      <div className={`min-h-screen ${isDarkMode ? 'bg-gray-900 text-white' : 'bg-white text-gray-900'}`}>
        <Transition.Root show={sidebarOpen} as={Fragment}>
          <Dialog as="div" className="relative z-50 lg:hidden" onClose={setSidebarOpen}>
            <Transition.Child
              as={Fragment}
              enter="transition-opacity ease-linear duration-300"
              enterFrom="opacity-0"
              enterTo="opacity-100"
              leave="transition-opacity ease-linear duration-300"
              leaveFrom="opacity-100"
              leaveTo="opacity-0"
            >
              <div className="fixed inset-0 bg-gray-900/80" />
            </Transition.Child>

            <div className="fixed inset-0 flex">
              <Transition.Child
                as={Fragment}
                enter="transition ease-in-out duration-300 transform"
                enterFrom="-translate-x-full"
                enterTo="translate-x-0"
                leave="transition ease-in-out duration-300 transform"
                leaveFrom="translate-x-0"
                leaveTo="-translate-x-full"
              >
                <Dialog.Panel className="relative mr-16 flex w-full max-w-xs flex-1">
                  <div className={`flex grow flex-col gap-y-5 overflow-y-auto px-6 pb-4 ring-1 ring-white/10 ${isDarkMode ? 'bg-gray-800' : 'bg-white'}`}>
                    <div className="flex h-16 shrink-0 items-center justify-between">
                      <Image
                        className="h-8 w-auto"
                        src={defaultLogo}
                        alt="SDHS Bot"
                        width={32}
                        height={32}
                        loading="eager"
                      />
                      <button
                        onClick={toggleDarkMode}
                        className={`rounded-lg p-2 hover:bg-gray-700 transition-colors ${isDarkMode ? 'text-yellow-500' : 'text-gray-500'}`}
                      >
                        {isDarkMode ? (
                          <SunIcon className="h-5 w-5" />
                        ) : (
                          <MoonIcon className="h-5 w-5" />
                        )}
                      </button>
                    </div>
                    {session && <ServerSelect />}
                    <nav className="flex flex-1 flex-col">
                      <ul role="list" className="flex flex-1 flex-col gap-y-7">
                        <li>
                          <ul role="list" className="-mx-2 space-y-1">
                            {navigation.map((item) => (
                              <li key={item.name}>
                                <button
                                  onClick={() => handleNavigation(item.href)}
                                  className={`
                                    group flex w-full gap-x-3 rounded-md p-2 text-sm font-semibold leading-6
                                    ${router.pathname === item.href
                                      ? isDarkMode
                                        ? 'bg-gray-700 text-white'
                                        : 'bg-gray-100 text-gray-900'
                                      : isDarkMode
                                        ? 'text-gray-400 hover:text-white hover:bg-gray-700'
                                        : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                                    }
                                  `}
                                >
                                  <item.icon className="h-6 w-6 shrink-0" aria-hidden="true" />
                                  {item.name}
                                </button>
                              </li>
                            ))}
                          </ul>
                        </li>
                      </ul>
                    </nav>
                  </div>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </Dialog>
        </Transition.Root>

        {/* Static sidebar for desktop */}
        <div className="hidden lg:fixed lg:inset-y-0 lg:z-50 lg:flex lg:w-72 lg:flex-col">
          <div className={`flex h-full flex-col gap-y-5 border-r px-6 ${isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
            <div className="flex h-16 shrink-0 items-center justify-between">
              <Image
                className="h-8 w-auto"
                src={defaultLogo}
                alt="SDHS Bot"
                width={32}
                height={32}
                loading="eager"
              />
              <button
                onClick={toggleDarkMode}
                className={`rounded-lg p-2 hover:bg-gray-700 transition-colors ${isDarkMode ? 'text-yellow-500' : 'text-gray-500'}`}
              >
                {isDarkMode ? (
                  <SunIcon className="h-5 w-5" />
                ) : (
                  <MoonIcon className="h-5 w-5" />
                )}
              </button>
            </div>
            <div className="flex-shrink-0">
              {session && <ServerSelect />}
            </div>
            <nav className="flex flex-1 flex-col">
              <ul role="list" className="flex flex-1 flex-col gap-y-7">
                <li>
                  <ul role="list" className="-mx-2 space-y-1">
                    {navigation.map((item) => (
                      <li key={item.name}>
                        <button
                          onClick={() => handleNavigation(item.href)}
                          className={`
                            group flex w-full gap-x-3 rounded-md p-2 text-sm font-semibold leading-6
                            ${router.pathname === item.href
                              ? isDarkMode
                                ? 'bg-gray-700 text-white'
                                : 'bg-gray-100 text-gray-900'
                              : isDarkMode
                                ? 'text-gray-400 hover:text-white hover:bg-gray-700'
                                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                            }
                          `}
                        >
                          <item.icon className="h-6 w-6 shrink-0" aria-hidden="true" />
                          {item.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                </li>
                <li className="mt-auto">
                  <div className={`flex items-center gap-x-4 px-6 py-3 text-sm font-semibold leading-6 ${isDarkMode ? 'text-white' : 'text-gray-900'}`}>
                    {session ? (
                      <>
                        <Image
                          className="h-8 w-8 rounded-full bg-gray-800"
                          src={session.user?.image || defaultLogo}
                          alt=""
                          width={32}
                          height={32}
                          loading="eager"
                        />
                        <span className="sr-only">Your profile</span>
                        <span aria-hidden="true">{session.user?.name}</span>
                        <button
                          onClick={() => signOut()}
                          className={`ml-auto ${isDarkMode ? 'text-gray-400 hover:text-white' : 'text-gray-500 hover:text-gray-900'}`}
                        >
                          Sign out
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => signIn('discord')}
                        className="flex items-center gap-x-2 text-discord-blurple hover:text-white"
                      >
                        Sign in with Discord
                      </button>
                    )}
                  </div>
                </li>
              </ul>
            </nav>
          </div>
        </div>

        <div className="lg:pl-72">
          <div className={`sticky top-0 z-40 flex h-16 shrink-0 items-center gap-x-4 border-b px-4 shadow-sm sm:gap-x-6 sm:px-6 lg:px-8 ${
            isDarkMode ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'
          }`}>
            <button
              type="button"
              className={`-m-2.5 p-2.5 lg:hidden ${isDarkMode ? 'text-gray-400' : 'text-gray-700'}`}
              onClick={() => setSidebarOpen(true)}
            >
              <span className="sr-only">Open sidebar</span>
              <Bars3Icon className="h-6 w-6" aria-hidden="true" />
            </button>

            {/* Separator */}
            <div className={`h-6 w-px lg:hidden ${isDarkMode ? 'bg-gray-700' : 'bg-gray-900/10'}`} aria-hidden="true" />

            <div className="flex flex-1 gap-x-4 self-stretch lg:gap-x-6">
              <div className="flex items-center gap-x-4 lg:gap-x-6">
                {session ? (
                  <div className="flex items-center gap-x-4">
                    <Image
                      className="h-8 w-8 rounded-full bg-gray-800 lg:hidden"
                      src={session.user?.image || defaultLogo}
                      alt=""
                      width={32}
                      height={32}
                      loading="eager"
                    />
                    <span className="sr-only">Your profile</span>
                    <span className={`lg:hidden ${isDarkMode ? 'text-white' : 'text-gray-900'}`} aria-hidden="true">
                      {session.user?.name}
                    </span>
                  </div>
                ) : (
                  <button
                    onClick={() => signIn('discord')}
                    className="lg:hidden flex items-center gap-x-2 text-discord-blurple hover:text-gray-900"
                  >
                    Sign in with Discord
                  </button>
                )}
              </div>
            </div>
          </div>

          <main className="py-10">
            <div className="px-4 sm:px-6 lg:px-8">{children}</div>
          </main>
        </div>
      </div>
    </div>
  )
} 