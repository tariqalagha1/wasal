import { useEffect, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'

interface AuditRow {
  id: number
  occurred_at: string
  actor_user_id: number | null
  action: string
  entity_type: string
  entity_id: number
  from_state: string | null
  to_state: string | null
  correlation_id: string
}

export default function AuditScreen() {
  const { t } = useI18n()
  const [rows, setRows] = useState<AuditRow[]>([])
  const [action, setAction] = useState('')

  const load = async () => {
    const q = action ? `?action=${encodeURIComponent(action)}` : ''
    const res = await api.get<{ audit: AuditRow[] }>(`/api/audit${q}`)
    setRows(res.audit)
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div>
      <h1>{t('audit')}</h1>
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <input placeholder={t('action')} value={action} onChange={(e) => setAction(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && load()} />
          <button className="btn ghost" onClick={load}>
            {t('search')}
          </button>
        </div>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>{t('occurredAt')}</th>
              <th>{t('actor')}</th>
              <th>{t('action')}</th>
              <th>{t('entity')}</th>
              <th>{t('from')}</th>
              <th>{t('to')}</th>
              <th>{t('correlationId')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 200).map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{new Date(r.occurred_at).toLocaleString()}</td>
                <td>{r.actor_user_id ?? '—'}</td>
                <td>{r.action}</td>
                <td>
                  {r.entity_type} #{r.entity_id}
                </td>
                <td>{r.from_state ?? '—'}</td>
                <td>{r.to_state ?? '—'}</td>
                <td className="muted">{r.correlation_id.slice(0, 8)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
