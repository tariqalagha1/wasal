import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { useI18n } from '../i18n'
import { useOrganization } from '../org'
import Clock from '../Clock'

export default function LoginScreen() {
  const { t } = useI18n()
  const { login, user } = useAuth()
  const { org } = useOrganization()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (user) {
      navigate(user.role === 'CASHIER' ? `/cashier/${user.username}` : '/check-in', { replace: true })
    }
  }, [user, navigate])

  if (user) return null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      const u = JSON.parse(localStorage.getItem('qms_user') || '{}')
      navigate(u.role === 'CASHIER' ? `/cashier/${u.username}` : '/check-in', { replace: true })
    } catch (err: any) {
      setError(err.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
      <form className="card" style={{ width: 360 }} onSubmit={submit}>
        <h1>
          {org.name || t('appName')} {import.meta.env.VITE_DEMO === 'true' && <span className="demo-badge">DEMO</span>}
        </h1>
        {org.tagline && <div className="muted" style={{ marginBottom: 12 }}>{org.tagline}</div>}
        <div style={{ marginBottom: 12 }}><Clock /></div>
        {error && <div className="error-box">{error}</div>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <label>
            <div className="muted">{t('username')}</div>
            <input placeholder={t('username')} value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
          </label>
          <label>
            <div className="muted">{t('password')}</div>
            <input type="password" placeholder={t('password')} value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <button className="btn" type="submit" disabled={loading}>
            {loading ? t('loading') : t('signIn')}
          </button>
          {import.meta.env.VITE_DEMO !== 'true' && (
            <div className="muted">admin / admin123 · reception / reception123 · WIN1..4 / cashier123</div>
          )}
        </div>
      </form>
    </div>
  )
}
