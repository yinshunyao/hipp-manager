import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Spin } from 'antd'
import AppLayout from './layouts/AppLayout'
import OpsLayout from './layouts/OpsLayout'
import LoginPage from './pages/LoginPage'
import ProfilePage from './pages/ProfilePage'
import WalletPage from './pages/WalletPage'
import TransactionsPage from './pages/TransactionsPage'
import BillsPage from './pages/BillsPage'
import OpsLoginPage from './pages/ops/OpsLoginPage'
import OpsUsersPage from './pages/ops/OpsUsersPage'
import OpsTransactionsPage from './pages/ops/OpsTransactionsPage'
import OpsRechargePage from './pages/ops/OpsRechargePage'
import OpsAdjustPage from './pages/ops/OpsAdjustPage'
import OpsPasswordPage from './pages/ops/OpsPasswordPage'
import { useAuthStore } from './store/auth'
import { useOpsStore } from './store/ops'
import { getToken } from './api/client'
import { getOpsToken } from './api/ops'

const basename = (import.meta.env.BASE_URL || '/').replace(/\/$/, '') || '/'

function Guard({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  const loading = useAuthStore((s) => s.loading)
  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
        <Spin />
      </div>
    )
  }
  if (!user && !getToken()) return <Navigate to="/login" replace />
  if (!user) return <Navigate to="/login" replace />
  return children
}

function OpsGuard({ children }: { children: React.ReactNode }) {
  const admin = useOpsStore((s) => s.admin)
  const loading = useOpsStore((s) => s.loading)
  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
        <Spin />
      </div>
    )
  }
  if (!admin && !getOpsToken()) return <Navigate to="/manager/login" replace />
  if (!admin) return <Navigate to="/manager/login" replace />
  return children
}

export default function App() {
  const hydrate = useAuthStore((s) => s.hydrate)
  const opsHydrate = useOpsStore((s) => s.hydrate)
  useEffect(() => {
    void hydrate()
    void opsHydrate()
  }, [hydrate, opsHydrate])

  return (
    <BrowserRouter basename={basename === '/' ? undefined : basename}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/manager/login" element={<OpsLoginPage />} />
        <Route
          path="/manager"
          element={
            <OpsGuard>
              <OpsLayout />
            </OpsGuard>
          }
        >
          <Route index element={<Navigate to="/manager/users" replace />} />
          <Route path="users" element={<OpsUsersPage />} />
          <Route path="transactions" element={<OpsTransactionsPage />} />
          <Route path="recharge" element={<OpsRechargePage />} />
          <Route path="adjust" element={<OpsAdjustPage />} />
          <Route path="password" element={<OpsPasswordPage />} />
        </Route>
        <Route
          path="/"
          element={
            <Guard>
              <AppLayout />
            </Guard>
          }
        >
          <Route index element={<Navigate to="/profile" replace />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="wallet" element={<WalletPage />} />
          <Route path="transactions" element={<TransactionsPage />} />
          <Route path="bills" element={<BillsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
