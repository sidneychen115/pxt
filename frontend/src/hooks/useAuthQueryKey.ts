import { useAuth } from '../context/AuthContext'

/** Prefix React Query keys with current user id so cached data never leaks across users. */
export function useAuthQueryKey(...parts: readonly unknown[]) {
  const { user } = useAuth()
  return [...parts, user?.id ?? 'none'] as const
}
