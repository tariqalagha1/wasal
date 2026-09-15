import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react'
import { api } from './api'

interface Org {
  name: string
  tagline: string
}

interface OrgCtx {
  org: Org
  refresh: () => Promise<void>
}

const Ctx = createContext<OrgCtx>({ org: { name: '', tagline: '' }, refresh: async () => {} })

export function OrganizationProvider({ children }: { children: ReactNode }) {
  const [org, setOrg] = useState<Org>({ name: '', tagline: '' })

  const refresh = useCallback(async () => {
    try {
      const r = await api.get<Org>('/api/settings/organization')
      setOrg({ name: r.name || '', tagline: r.tagline || '' })
    } catch {
      // keep current/fallback values
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return <Ctx.Provider value={{ org, refresh }}>{children}</Ctx.Provider>
}

export function useOrganization() {
  return useContext(Ctx)
}
