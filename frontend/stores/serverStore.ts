import { create } from 'zustand';
import { Guild } from '@/lib/api';

interface ServerStore {
  selectedServer: Guild | null;
  setSelectedServer: (server: Guild | null) => void;
}

export const useServerStore = create<ServerStore>((set) => ({
  selectedServer: null,
  setSelectedServer: (server) => set({ selectedServer: server }),
})); 