import { useParams } from 'react-router-dom'
import { useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import { useOnline, useLive } from '../hooks'

interface Waiting {
  id: number
  ticket_number: number
  visit_type: string
}

interface Cashier {
  id: number
  code: string
  display_name: string
  current_ticket_id: number | null
  current_ticket: number | null
  current_status: string | null
}

export default function CashierScreen() {
  const { cashierId } = useParams()
  const { t } = useI18n()
  const online = useOnline()
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const cashiers = useLive<{ cashiers: Cashier[] }>(
    () => api.get('/api/cashiers'),
    4000,
    ['cashier.state_changed', 'ticket.called', 'ticket.completed', 'ticket.no_show', 'ticket.serving'],
  )
  const waiting = useLive<{ waiting: Waiting[] }>(
    () => api.get('/api/queue/waiting'),
    4000,
    ['ticket.checked_in', 'ticket.called', 'ticket.returned_to_queue', 'ticket.cancelled', 'queue.updated'],
  )

  const me = cashiers?.cashiers.find((c) => String(c.id) === cashierId || c.code === cashierId)
  const current = me?.current_ticket ?? null
  const currentStatus = me?.current_status ?? null
  const currentId = me?.current_ticket_id ?? null

  const act = async (path: string, body?: unknown) => {
    setError('')
    setSuccess('')
    try {
      const res: any = await api.post(path, body)
      if (res && res.result === 'QUEUE_EMPTY') {
        setError(t('queueEmpty'))
      } else {
        setSuccess(t('success'))
      }
      return res
    } catch (e: any) {
      setError(e.message)
    }
  }

  return (
    <div>
      <h1>
        {t('cashier')} — {me?.display_name || cashierId}
      </h1>
      {error && <div className="error-box">{error}</div>}
      {success && <div className="success-box">{success}</div>}

      <div className="card" style={{ textAlign: 'center' }}>
        <div className="muted">{t('currentTicket')}</div>
        <div style={{ fontSize: '4rem', fontWeight: 800 }}>{current ?? '—'}</div>
        <div>
          <span className={`pill ${(currentStatus || '').toLowerCase()}`}>{currentStatus ? t(currentStatus.toLowerCase()) : ''}</span>
        </div>
        <div className="row" style={{ justifyContent: 'center', marginTop: 16 }}>
          <button className="btn" disabled={!online || !!current || (waiting?.waiting.length ?? 0) === 0} onClick={() => act(`/api/cashiers/${me?.id}/call-next`)}>
            {t('callNext')}
          </button>
          <button className="btn ghost" disabled={!online || currentStatus !== 'CALLED'} onClick={() => act(`/api/tickets/${currentId}/recall`)}>
            {t('recall')}
          </button>
          <button className="btn" disabled={!online || currentStatus !== 'CALLED'} onClick={() => act(`/api/tickets/${currentId}/start`)}>
            {t('startServing')}
          </button>
          <button className="btn ghost" disabled={!online || currentStatus !== 'CALLED'} onClick={() => act(`/api/tickets/${currentId}/no-show`)}>
            {t('markNoShow')}
          </button>
          <button className="btn" disabled={!online || currentStatus !== 'SERVING'} onClick={() => act(`/api/tickets/${currentId}/done`)}>
            {t('markDone')}
          </button>
        </div>
      </div>

      <div className="card">
        <h2>
          {t('waiting')} ({waiting?.waiting.length ?? 0})
        </h2>
        {!waiting || waiting.waiting.length === 0 ? (
          <div className="muted">{t('noWaiting')}</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>{t('ticketNumber')}</th>
                <th>{t('visitType')}</th>
              </tr>
            </thead>
            <tbody>
              {waiting.waiting.map((w) => (
                <tr key={w.id}>
                  <td style={{ fontWeight: 700 }}>{w.ticket_number}</td>
                  <td>{t(w.visit_type.toLowerCase())}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
