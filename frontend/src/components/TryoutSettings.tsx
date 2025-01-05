import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getServerTryouts, createTryout, updateTryout, deleteTryout } from '@/lib/api';
import { useServerStore } from '@/lib/store';
import { PlusIcon, TrashIcon, PencilIcon } from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';

interface TryoutGroup {
  group_id: string;
  description: string;
  event_name: string;
  requirements: string[];
  ping_roles: string[];
}

export default function TryoutSettings() {
  const [isEditing, setIsEditing] = useState<string | null>(null);
  const [newGroup, setNewGroup] = useState(false);
  const selectedServer = useServerStore((state) => state.selectedServer);
  const queryClient = useQueryClient();

  const { data: tryoutGroups, isLoading } = useQuery({
    queryKey: ['tryoutGroups', selectedServer?.id],
    queryFn: () => getServerTryouts(selectedServer!.id),
    enabled: !!selectedServer,
  });

  const createMutation = useMutation({
    mutationFn: (data: Omit<TryoutGroup, 'group_id'>) =>
      createTryout(selectedServer!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries(['tryoutGroups', selectedServer?.id]);
      toast.success('Tryout group created successfully');
      setNewGroup(false);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to create tryout group');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ groupId, data }: { groupId: string; data: Partial<TryoutGroup> }) =>
      updateTryout(selectedServer!.id, groupId, data),
    onSuccess: () => {
      queryClient.invalidateQueries(['tryoutGroups', selectedServer?.id]);
      toast.success('Tryout group updated successfully');
      setIsEditing(null);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to update tryout group');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (groupId: string) => deleteTryout(selectedServer!.id, groupId),
    onSuccess: () => {
      queryClient.invalidateQueries(['tryoutGroups', selectedServer?.id]);
      toast.success('Tryout group deleted successfully');
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to delete tryout group');
    },
  });

  if (!selectedServer) {
    return (
      <div className="text-center text-gray-500 dark:text-gray-400">
        Please select a server to manage tryout settings
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
          Tryout Groups
        </h2>
        <button
          onClick={() => setNewGroup(true)}
          className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
        >
          <PlusIcon className="h-5 w-5 mr-2" />
          Add Group
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="animate-pulse bg-gray-100 dark:bg-gray-800 rounded-lg p-6"
            >
              <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/4 mb-4" />
              <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4" />
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          {newGroup && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const formData = new FormData(e.currentTarget);
                createMutation.mutate({
                  event_name: formData.get('event_name') as string,
                  description: formData.get('description') as string,
                  requirements: (formData.get('requirements') as string).split('\n').filter(Boolean),
                  ping_roles: [],
                });
              }}
              className="bg-white dark:bg-gray-800 rounded-lg p-6 space-y-4"
            >
              <div>
                <label htmlFor="event_name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Event Name
                </label>
                <input
                  type="text"
                  name="event_name"
                  id="event_name"
                  required
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                />
              </div>
              <div>
                <label htmlFor="description" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Description
                </label>
                <textarea
                  name="description"
                  id="description"
                  required
                  rows={3}
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                />
              </div>
              <div>
                <label htmlFor="requirements" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Requirements (one per line)
                </label>
                <textarea
                  name="requirements"
                  id="requirements"
                  rows={3}
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                />
              </div>
              <div className="flex justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setNewGroup(false)}
                  className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-600"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                >
                  Create
                </button>
              </div>
            </form>
          )}

          {tryoutGroups?.map((group: TryoutGroup) => (
            <div
              key={group.group_id}
              className="bg-white dark:bg-gray-800 rounded-lg p-6 space-y-4"
            >
              {isEditing === group.group_id ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    const formData = new FormData(e.currentTarget);
                    updateMutation.mutate({
                      groupId: group.group_id,
                      data: {
                        event_name: formData.get('event_name') as string,
                        description: formData.get('description') as string,
                        requirements: (formData.get('requirements') as string).split('\n').filter(Boolean),
                      },
                    });
                  }}
                  className="space-y-4"
                >
                  <div>
                    <label htmlFor="event_name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                      Event Name
                    </label>
                    <input
                      type="text"
                      name="event_name"
                      id="event_name"
                      defaultValue={group.event_name}
                      required
                      className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                    />
                  </div>
                  <div>
                    <label htmlFor="description" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                      Description
                    </label>
                    <textarea
                      name="description"
                      id="description"
                      defaultValue={group.description}
                      required
                      rows={3}
                      className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                    />
                  </div>
                  <div>
                    <label htmlFor="requirements" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                      Requirements (one per line)
                    </label>
                    <textarea
                      name="requirements"
                      id="requirements"
                      defaultValue={group.requirements.join('\n')}
                      rows={3}
                      className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white sm:text-sm"
                    />
                  </div>
                  <div className="flex justify-end space-x-3">
                    <button
                      type="button"
                      onClick={() => setIsEditing(null)}
                      className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-600"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                    >
                      Save
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                        {group.event_name}
                      </h3>
                      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        {group.description}
                      </p>
                    </div>
                    <div className="flex space-x-2">
                      <button
                        onClick={() => setIsEditing(group.group_id)}
                        className="p-2 text-gray-400 hover:text-gray-500 dark:hover:text-gray-300"
                      >
                        <PencilIcon className="h-5 w-5" />
                      </button>
                      <button
                        onClick={() => {
                          if (window.confirm('Are you sure you want to delete this tryout group?')) {
                            deleteMutation.mutate(group.group_id);
                          }
                        }}
                        className="p-2 text-red-400 hover:text-red-500"
                      >
                        <TrashIcon className="h-5 w-5" />
                      </button>
                    </div>
                  </div>
                  {group.requirements.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Requirements:
                      </h4>
                      <ul className="mt-2 list-disc list-inside text-sm text-gray-500 dark:text-gray-400">
                        {group.requirements.map((req, index) => (
                          <li key={index}>{req}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
} 