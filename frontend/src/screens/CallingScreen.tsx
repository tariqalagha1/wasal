import { useEffect } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import { useOrganization } from '../org'
import { useOnline, useLive } from '../hooks'
import Clock from '../Clock'

interface CallingState {
  current: { ticket_number: number; window: string } | null
  recent: { ticket_number: number; window: string }[]
}

export default function CallingScreen() {
  const { t, setLocale } = useI18n()
  const { org } = useOrganization()
  const online = useOnline()

  useEffect(() => {
    api
      .get<{ locale: 'en' | 'ar' }>('/api/settings/language?scope=calling_screen')
      .then((r) => setLocale(r.locale))
      .catch(() => {})
  }, [setLocale])

  const state = useLive<CallingState>(
    () => api.get('/api/calling-screen/state'),
    2000,
    ['ticket.called', 'ticket.recalled', 'ticket.completed'],
  )

  return (
    <div className="calling-screen">
      {import.meta.env.VITE_DEMO === 'true' && <div className="demo-badge" style={{ position: 'absolute', top: 16, insetInlineStart: 16 }}>DEMO</div>}
      {!online && <div className="offline-banner">{t('offline')}</div>}
      <div className="school">{org.name || t('appName')}</div>
      {org.tagline && <div className="school-tagline">{org.tagline}</div>}
      <div className="clock"><Clock full /></div>
      <div className="now">{t('nowServing')}</div>
      {state?.current ? (
        <>
          <div className="ticket">{t('ticket')} {state.current.ticket_number}</div>
          <div className="window">{state.current.window}</div>
        </>
      ) : (
        <div className="ticket" style={{ opacity: 0.4 }}>
          —
        </div>
      )}
      <div className="recent">
        {state?.recent.slice(0, 8).map((r, i) => (
          <div key={i}>
            {t('ticket')} {r.ticket_number} — {r.window}
          </div>
        ))}
      </div>
    </div>
  )
}
