import { useEffect } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import { useOnline, useLive } from '../hooks'

interface DisplayState {
  service_date: string
  waiting_count: number
  cashiers: { id: number; display_name: string; current_ticket: number | null; current_status: string | null }[]
  recent: { ticket_number: number; window: string; status: string }[]
}

export default function DisplayScreen() {
  const { t, setLocale } = useI18n()
  const online = useOnline()

  useEffect(() => {
    api
      .get<{ locale: 'en' | 'ar' }>('/api/settings/language?scope=public_display')
      .then((r) => setLocale(r.locale))
      .catch(() => {})
  }, [setLocale])

  const state = useLive<DisplayState>(
    () => api.get('/api/display/state'),
    3000,
    ['ticket.called', 'ticket.completed', 'ticket.checked_in', 'ticket.no_show', 'ticket.recalled', 'queue.updated'],
  )

  return (
    <div style={{ padding: 20 }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h1>
          {t('appName')} {import.meta.env.VITE_DEMO === 'true' && <span className="demo-badge">DEMO</span>}
        </h1>
        <span className={`net ${online ? 'ok' : 'bad'}`}>{online ? t('online') : t('offline')}</span>
      </div>
      <div className="grid">
        {state?.cashiers.map((c) => (
          <div className="display-cashier" key={c.id}>
            <div className="win">{c.display_name}</div>
            <div className="num">{c.current_ticket ?? '—'}</div>
            <div className="st">{c.current_status ? t(c.current_status.toLowerCase()) : ''}</div>
          </div>
        ))}
      </div>
      <div className="card" style={{ marginTop: 20 }}>
        <h2>
          {t('waitingCount')}: {state?.waiting_count ?? 0}
        </h2>
        <div className="row" style={{ flexWrap: 'wrap' }}>
          {state?.recent.map((r, i) => (
            <span key={i} className="pill serving">
              {t('ticket')} {r.ticket_number} — {r.window}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
