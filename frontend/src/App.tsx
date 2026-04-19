import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Strategies from './pages/Strategies'
import Signals from './pages/Signals'
import Backtests from './pages/Backtests'
import BacktestPresets from './pages/BacktestPresets'
import System from './pages/System'

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/strategies" element={<Strategies />} />
          <Route path="/signals" element={<Signals />} />
          <Route path="/backtests/presets" element={<BacktestPresets />} />
          <Route path="/backtests" element={<Backtests />} />
          <Route path="/backtests/:id" element={<Backtests />} />
          <Route path="/system" element={<System />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
