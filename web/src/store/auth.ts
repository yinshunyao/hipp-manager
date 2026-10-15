import { create } from 'zustand'
import type { UserProfile } from '../api/auth'
import { fetchMe, logoutRemote } from '../api/auth'
import { getToken, setToken } from '../api/client'
import { broadcastLogout, onRemoteLogout, shouldClearLocal } from '../api/sso'

type AuthState = {
  user: UserProfile | null
  loading: boolean
  hydrate: () => Promise<void>
  setUser: (user: UserProfile | null) => void
  logout: () => void
}

function clearLocal(set: (p: Partial<AuthState>) => void) {
  setToken(null)
  set({ user: null, loading: false })
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true,
  setUser: (user) => set({ user }),
  logout: () => {
    void logoutRemote().finally(() => {
      broadcastLogout()
      clearLocal(set)
    })
  },
  hydrate: async () => {
    if (shouldClearLocal('mgr')) {
      clearLocal(set)
      return
    }
    if (!getToken()) {
      set({ user: null, loading: false })
      return
    }
    try {
      const user = await fetchMe()
      set({ user, loading: false })
    } catch {
      clearLocal(set)
    }
  },
}))

if (typeof window !== 'undefined') {
  onRemoteLogout(() => {
    clearLocal(useAuthStore.setState)
  })
}
