import type { ReactNode } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { LayoutDashboard, TrendingUp, Bell, BarChart2, Activity, Wallet } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

const nav = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard', match: 'exact' as const },
  { to: '/strategies', icon: TrendingUp, label: 'Strategies', match: 'exact' as const },
  { to: '/signals', icon: Bell, label: 'Signals', match: 'exact' as const },
  { to: '/positions', icon: Wallet, label: 'Positions', match: 'exact' as const },
  { to: '/backtests', icon: BarChart2, label: 'Backtests', match: 'backtests' as const },
  { to: '/system', icon: Activity, label: 'System', match: 'exact' as const },
]

function linkActive(pathname: string, match: (typeof nav)[number]['match'], to: string): boolean {
  if (match === 'backtests') {
    return pathname === '/backtests' || /^\/backtests\/\d+$/.test(pathname) || pathname === '/backtests/presets'
  }
  return pathname === to
}

export default function Layout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { user, clearUser } = useAuth()

  const switchUser = () => {
    clearUser()
    navigate('/login')
  }

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      <nav className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col p-4 gap-1">
        <div className="text-xl font-bold text-white mb-3 px-2">PXT Trading</div>
        <div
          className="mx-1 mb-4 rounded-xl border-2 border-blue-500/50 bg-gradient-to-br from-blue-950/90 to-gray-900 p-3 shadow-lg shadow-blue-950/40"
          aria-label={`当前用户 ${user?.username ?? ''}`}
        >
          <p className="text-[10px] font-semibold uppercase tracking-widest text-blue-300 mb-2">
            当前用户
          </p>
          <div className="flex items-center gap-3">
            <div
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-600 text-sm font-bold text-white ring-2 ring-blue-400/60"
              aria-hidden
            >
              {(user?.username ?? '?').slice(0, 2).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-lg font-bold leading-tight text-white">{user?.username}</p>
              <p className="text-[11px] text-blue-200/70">已登录</p>
            </div>
          </div>
          <button
            type="button"
            onClick={switchUser}
            className="mt-3 w-full rounded-lg border border-blue-500/40 bg-blue-600/20 px-2 py-1.5 text-xs font-medium text-blue-200 transition-colors hover:bg-blue-600/40 hover:text-white"
          >
            切换用户
          </button>
        </div>
        {nav.map(({ to, icon: Icon, label, match }) => {
          const isActive =
            match === 'exact' ? pathname === to : linkActive(pathname, match, to)
          return (
            <NavLink
              key={to}
              to={to}
              className={() =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-gray-100'
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          )
        })}
      </nav>
      <main className="flex-1 overflow-auto p-6">{children}</main>
    </div>
  )
}
