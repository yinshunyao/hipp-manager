import { create } from 'zustand'
import { getOpsToken, opsLogout, opsMe, type OpsAdmin } from '../api/ops'

type OpsState = {
  admin: OpsAdmin | null
  loading: boolean
  hydrate: () => Promise<void>
  setAdmin: (admin: OpsAdmin | null) => void
  logout: () => void
}

export const useOpsStore = create<OpsState>((set) => ({
  admin: null,
  loading: true,
  setAdmin: (admin) => set({ admin }),
  logout: () => {
    void opsLogout().finally(() => set({ admin: null, loading: false }))
  },
  hydrate: async () => {
    if (!getOpsToken()) {
      set({ admin: null, loading: false })
      return
    }
    try {
      const admin = await opsMe()
      set({ admin, loading: false })
    } catch {
      set({ admin: null, loading: false })
    }
  },
}))
