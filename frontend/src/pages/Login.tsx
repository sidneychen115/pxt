import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { fetchAuthUsers } from '../api/auth'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const navigate = useNavigate()
  const { setUser } = useAuth()
  const { data: users, isLoading, error } = useQuery({
    queryKey: ['auth-users'],
    queryFn: fetchAuthUsers,
  })

  const pick = (id: number, username: string) => {
    setUser({ id, username })
    navigate('/dashboard', { replace: true })
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-6">
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 w-full max-w-sm space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-white">PXT Trading</h1>
          <p className="text-gray-400 text-sm mt-1">Select user to continue</p>
        </div>
        {isLoading && <p className="text-gray-500 text-sm">Loading users…</p>}
        {error && <p className="text-red-400 text-sm">Cannot load users. Is the backend running?</p>}
        <div className="flex flex-col gap-2">
          {users?.map(u => (
            <button
              key={u.id}
              type="button"
              onClick={() => pick(u.id, u.username)}
              className="w-full py-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold"
            >
              {u.username}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
