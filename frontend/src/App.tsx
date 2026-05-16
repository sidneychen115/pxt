import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import RequireAuth from './components/RequireAuth'
import Dashboard from './pages/Dashboard'
import Strategies from './pages/Strategies'
import Signals from './pages/Signals'
import Positions from './pages/Positions'
import Backtests from './pages/Backtests'
import BacktestPresets from './pages/BacktestPresets'
import System from './pages/System'
import Login from './pages/Login'
import { AuthProvider } from './context/AuthContext'

function AuthedLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <Layout>{children}</Layout>
    </RequireAuth>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route
            path="/dashboard"
            element={
              <AuthedLayout>
                <Dashboard />
              </AuthedLayout>
            }
          />
          <Route
            path="/strategies"
            element={
              <AuthedLayout>
                <Strategies />
              </AuthedLayout>
            }
          />
          <Route
            path="/signals"
            element={
              <AuthedLayout>
                <Signals />
              </AuthedLayout>
            }
          />
          <Route
            path="/positions"
            element={
              <AuthedLayout>
                <Positions />
              </AuthedLayout>
            }
          />
          <Route
            path="/backtests/presets"
            element={
              <AuthedLayout>
                <BacktestPresets />
              </AuthedLayout>
            }
          />
          <Route
            path="/backtests"
            element={
              <AuthedLayout>
                <Backtests />
              </AuthedLayout>
            }
          />
          <Route
            path="/backtests/:id"
            element={
              <AuthedLayout>
                <Backtests />
              </AuthedLayout>
            }
          />
          <Route
            path="/system"
            element={
              <AuthedLayout>
                <System />
              </AuthedLayout>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
