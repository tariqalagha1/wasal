import { useEffect, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import { useOnline, useLive } from '../hooks'
import DisplayCanvas, { DisplayConfig, QueueData } from '../DisplayCanvas'

export default function DisplayScreen() {
  const { setLocale } = useI18n()
  const online = useOnline()
  const [config, setConfig] = useState<DisplayConfig | null>(null)

  useEffect(() => {
    api
      .get<{ locale: 'en' | 'ar' }>('/api/settings/language?scope=public_display')
      .then((r) => setLocale(r.locale))
      .catch(() => {})
    api.get<DisplayConfig>('/api/display-config').then(setConfig).catch(() => {})
  }, [setLocale])

  const data = useLive<QueueData>(
    () => api.get('/api/public-display/state'),
    3000,
    [
      'ticket.called',
      'ticket.completed',
      'ticket.checked_in',
      'ticket.no_show',
      'ticket.recalled',
      'ticket.returned_to_queue',
      'ticket.cancelled',
      'ticket.serving',
      'queue.updated',
      'cashier.state_changed',
    ],
  )

  return (
    <div style={{ position: 'fixed', inset: 0 }}>
      {config && <DisplayCanvas config={config} data={data} />}
      {!online && <div className="offline-banner">{online ? '' : 'Offline — reconnecting…'}</div>}
    </div>
  )
}
