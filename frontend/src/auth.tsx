import { createContext, useContext, useState, ReactNode } from 'react'
import { api, setToken as persistToken, getToken } from './api'

interface User {
  id: number
  username: string
  role: 'RECEPTIONIST' | 'CASHIER' | 'ADMIN'
  preferred_locale: 'en' | 'ar'
}

interface AuthCtx {
  user: User | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const Ctx = createContext<AuthCtx>({ user: null, login: async () => {}, logout: () => {} })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const cached = localStorage.getItem('qms_user')
    return cached ? (JSON.parse(cached) as User) : null
  })

  const login = async (username: string, password: string) => {
    const res = await api.post<{ token: string; user: User }>('/api/auth/login', { username, password })
    persistToken(res.token)
    localStorage.setItem('qms_user', JSON.stringify(res.user))
    setUser(res.user)
  }

  const logout = () => {
    persistToken(null)
    localStorage.removeItem('qms_user')
    setUser(null)
  }

  return <Ctx.Provider value={{ user, login, logout }}>{children}</Ctx.Provider>
}

export function useAuth() {
  return useContext(Ctx)
}

export function isAuthenticated(): boolean {
  return !!getToken()
}
