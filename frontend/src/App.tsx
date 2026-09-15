import { Navigate, Route, Routes, Link } from 'react-router-dom'
import { useAuth } from './auth'
import { useI18n } from './i18n'
import { useOrganization } from './org'
import { useOnline } from './hooks'
import Clock from './Clock'
import LoginScreen from './screens/LoginScreen'
import CheckInScreen from './screens/CheckInScreen'
import CashierScreen from './screens/CashierScreen'
import DisplayScreen from './screens/DisplayScreen'
import CallingScreen from './screens/CallingScreen'
import AdminScreen from './screens/AdminScreen'
import ReportsScreen from './screens/ReportsScreen'
import AuditScreen from './screens/AuditScreen'
import SettingsScreen from './screens/SettingsScreen'
import DisplayDesignerScreen from './screens/DisplayDesignerScreen'

function RequireAuth({ children, roles }: { children: JSX.Element; roles?: string[] }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (roles && !roles.includes(user.role)) {
    const home = user.role === 'CASHIER' ? `/cashier/${user.username}` : '/check-in'
    return <Navigate to={home} replace />
  }
  return children
}

function Layout({ children }: { children: JSX.Element }) {
  const { t } = useI18n()
  const { user, logout } = useAuth()
  const { org } = useOrganization()
  const online = useOnline()
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">{org.name || t('appName')}</div>
        {import.meta.env.VITE_DEMO === 'true' && <span className="demo-badge">DEMO</span>}
        {user && (
          <nav>
            {(user.role === 'RECEPTIONIST' || user.role === 'ADMIN') && <Link to="/check-in">{t('checkIn')}</Link>}
            {user.role === 'CASHIER' && <Link to={`/cashier/${user.username}`}>{t('cashier')}</Link>}
            {user.role === 'ADMIN' && (
              <>
                <Link to="/admin">{t('admin')}</Link>
                <Link to="/admin/display-designer">{t('displayDesigner')}</Link>
                <Link to="/reports">{t('reports')}</Link>
                <Link to="/audit">{t('audit')}</Link>
              </>
            )}
            <Link to="/settings">{t('settings')}</Link>
            <button className="link" onClick={logout}>
              {t('logout')} ({user.username})
            </button>
          </nav>
        )}
        <span className="clock-inline"><Clock /></span>
        <span className={`net ${online ? 'ok' : 'bad'}`}>{online ? t('online') : t('offline')}</span>
      </header>
      {!online && <div className="offline-banner">{t('offline')}</div>}
      <main>{children}</main>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginScreen />} />
      <Route path="/display" element={<DisplayScreen />} />
      <Route path="/calling-screen" element={<CallingScreen />} />
      <Route
        path="/check-in"
        element={
          <RequireAuth roles={['RECEPTIONIST', 'ADMIN']}>
            <Layout>
              <CheckInScreen />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/cashier/:cashierId"
        element={
          <RequireAuth roles={['CASHIER', 'ADMIN']}>
            <Layout>
              <CashierScreen />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/admin"
        element={
          <RequireAuth roles={['ADMIN']}>
            <Layout>
              <AdminScreen />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/reports"
        element={
          <RequireAuth roles={['ADMIN']}>
            <Layout>
              <ReportsScreen />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/audit"
        element={
          <RequireAuth roles={['ADMIN']}>
            <Layout>
              <AuditScreen />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/admin/display-designer"
        element={
          <RequireAuth roles={['ADMIN']}>
            <Layout>
              <DisplayDesignerScreen />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/settings"
        element={
          <RequireAuth>
            <Layout>
              <SettingsScreen />
            </Layout>
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}
