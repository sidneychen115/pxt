import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { LayoutDashboard, TrendingUp, Bell, BarChart2, Activity } from 'lucide-react'

const nav = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/strategies', icon: TrendingUp, label: 'Strategies' },
  { to: '/signals', icon: Bell, label: 'Signals' },
  { to: '/backtests', icon: BarChart2, label: 'Backtests' },
  { to: '/system', icon: Activity, label: 'System' },
]

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      <nav className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col p-4 gap-1">
        <div className="text-xl font-bold text-white mb-6 px-2">PXT Trading</div>
        {nav.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
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
        ))}
      </nav>
      <main className="flex-1 overflow-auto p-6">{children}</main>
    </div>
  )
}
