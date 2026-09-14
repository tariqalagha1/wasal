import { useEffect, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'

interface ImportSummary {
  status: string
  read: number
  inserted: number
  updated: number
  rejected: number
}

interface UserRow {
  id: number
  username: string
  role: string
  preferred_locale: string
  active: boolean
}

interface CashierRow {
  id: number
  code: string
  display_name: string
  active: boolean
  sort_order: number
}

export default function AdminScreen() {
  const { t } = useI18n()
  const [imports, setImports] = useState<any[]>([])
  const [users, setUsers] = useState<UserRow[]>([])
  const [cashiers, setCashiers] = useState<CashierRow[]>([])
  const [msg, setMsg] = useState('')

  const runImport = async () => {
    setMsg('')
    try {
      const r = await api.post<ImportSummary>('/api/imports/today')
      setMsg(`${t('importStatus')}: ${r.status} (${r.inserted} new, ${r.updated} updated, ${r.rejected} rejected)`)
      loadAll()
    } catch (e: any) {
      setMsg(e.message)
    }
  }

  const loadAll = async () => {
    try {
      setImports((await api.get<{ imports: any[] }>('/api/imports')).imports)
      setUsers((await api.get<{ users: UserRow[] }>('/api/users')).users)
      setCashiers((await api.get<{ cashiers: CashierRow[] }>('/api/admin/cashiers')).cashiers)
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div>
      <h1>{t('admin')}</h1>
      <div className="card">
        <div className="row">
          <button className="btn" onClick={runImport}>
            {t('runImport')}
          </button>
          <button className="btn ghost" onClick={loadAll}>
            {t('importStatus')}
          </button>
        </div>
        {msg && <div className="success-box">{msg}</div>}
        <h2>{t('importStatus')}</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Date</th>
              <th>Status</th>
              <th>Read</th>
              <th>Inserted</th>
              <th>Updated</th>
              <th>Rejected</th>
            </tr>
          </thead>
          <tbody>
            {imports.slice(0, 10).map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.service_date}</td>
                <td>
                  <span className={`pill ${r.status.toLowerCase()}`}>{r.status}</span>
                </td>
                <td>{r.read_count}</td>
                <td>{r.inserted_count}</td>
                <td>{r.updated_count}</td>
                <td>{r.rejected_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>{t('users')}</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>{t('username')}</th>
              <th>{t('role')}</th>
              <th>{t('language')}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.id}</td>
                <td>{u.username}</td>
                <td>{u.role}</td>
                <td>{u.preferred_locale}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>{t('cashiers')}</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Code</th>
              <th>{t('window')}</th>
              <th>Active</th>
            </tr>
          </thead>
          <tbody>
            {cashiers.map((c) => (
              <tr key={c.id}>
                <td>{c.id}</td>
                <td>{c.code}</td>
                <td>{c.display_name}</td>
                <td>{c.active ? '✓' : '✗'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
