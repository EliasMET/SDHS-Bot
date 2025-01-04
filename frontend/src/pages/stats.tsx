import { useSession } from 'next-auth/react'

export default function Stats() {
  const { data: session } = useSession()

  if (!session) {
    return (
      <div className="text-center">
        <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-6xl">
          Access Denied
        </h1>
        <p className="mt-6 text-lg leading-8 text-gray-600">
          Please sign in to view statistics.
        </p>
      </div>
    )
  }

  return (
    <div>
      <div className="md:flex md:items-center md:justify-between">
        <div className="min-w-0 flex-1">
          <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:truncate sm:text-3xl sm:tracking-tight">
            Statistics
          </h2>
        </div>
      </div>
      
      <div className="mt-8">
        {/* Stats content will go here */}
        <p className="text-gray-600">Statistics features coming soon...</p>
      </div>
    </div>
  )
} 