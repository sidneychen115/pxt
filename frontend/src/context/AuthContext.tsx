import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

const STORAGE_KEY = 'pxt_user_id'
const STORAGE_NAME_KEY = 'pxt_username'

export type AuthUser = { id: number; username: string }

type AuthContextValue = {
  user: AuthUser | null
  setUser: (user: AuthUser) => void
  clearUser: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUserState] = useState<AuthUser | null>(null)

  useEffect(() => {
    const id = localStorage.getItem(STORAGE_KEY)
    const username = localStorage.getItem(STORAGE_NAME_KEY)
    if (id && username) {
      setUserState({ id: Number(id), username })
    }
  }, [])

  const setUser = useCallback(
    (u: AuthUser) => {
      localStorage.setItem(STORAGE_KEY, String(u.id))
      localStorage.setItem(STORAGE_NAME_KEY, u.username)
      queryClient.clear()
      setUserState(u)
    },
    [queryClient],
  )

  const clearUser = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem(STORAGE_NAME_KEY)
    queryClient.clear()
    setUserState(null)
  }, [queryClient])

  const value = useMemo(() => ({ user, setUser, clearUser }), [user, setUser, clearUser])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
