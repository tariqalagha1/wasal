import { useEffect, useState } from 'react'
import { api, newIdempotencyKey } from '../api'
import { useI18n } from '../i18n'
import { useOrganization } from '../org'

interface Appt {
  id: number
  booking_number: string
  scheduled_at: string
  status: string
  guardian_id: number
  guardian_name: string
  phone: string
  student_name: string
}

export default function CheckInScreen() {
  const { t } = useI18n()
  const { org } = useOrganization()
  const [search, setSearch] = useState('')
  const [appts, setAppts] = useState<Appt[]>([])
  const [selected, setSelected] = useState<number[]>([])
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const [walkInName, setWalkInName] = useState('')
  const [walkInPhone, setWalkInPhone] = useState('')
  const [loading, setLoading] = useState(false)

  const load = async () => {
    try {
      const res = await api.get<{ appointments: Appt[] }>(`/api/appointments/today${search ? `?search=${encodeURIComponent(search)}` : ''}`)
      setAppts(res.appointments)
    } catch (e: any) {
      setMessage({ ok: false, text: e.message })
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const toggle = (id: number) => {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  }

  const checkIn = async () => {
    if (selected.length === 0) return
    const guardianId = appts.find((a) => a.id === selected[0])?.guardian_id
    setLoading(true)
    try {
      const res = await api.post<{ ticket: { id: number; ticket_number: number }; visit: { visit_type: string } }>(
        '/api/check-ins',
        { guardian_id: guardianId, appointment_ids: selected },
        { 'Idempotency-Key': newIdempotencyKey() },
      )
      setMessage({ ok: true, text: `${t('ticket')} ${res.ticket.ticket_number} · ${t(res.visit.visit_type.toLowerCase())}` })
      setSelected([])
      await load()
    } catch (e: any) {
      setMessage({ ok: false, text: e.message })
    } finally {
      setLoading(false)
    }
  }

  const walkIn = async () => {
    if (!walkInName.trim()) return
    setLoading(true)
    try {
      const res = await api.post<{ ticket: { id: number; ticket_number: number }; visit: { visit_type: string } }>(
        '/api/walk-ins',
        { name: walkInName.trim(), phone: walkInPhone.trim() || undefined },
        { 'Idempotency-Key': newIdempotencyKey() },
      )
      setMessage({ ok: true, text: `${t('ticket')} ${res.ticket.ticket_number} · ${t('walkIn')}` })
      setWalkInName('')
      setWalkInPhone('')
      await load()
    } catch (e: any) {
      setMessage({ ok: false, text: e.message })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      {(org.name || org.tagline) && (
        <div className="org-banner">
          {org.name && <div className="org-name">{org.name}</div>}
          {org.tagline && <div className="org-tagline">{org.tagline}</div>}
        </div>
      )}
      <h1>{t('checkIn')}</h1>
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <input
            placeholder={t('searchPlaceholder')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && load()}
            style={{ flex: 1 }}
          />
          <button className="btn ghost" onClick={load}>
            {t('search')}
          </button>
        </div>
        {message && <div className={message.ok ? 'success-box' : 'error-box'}>{message.text}</div>}
        {appts.length === 0 ? (
          <div className="muted">{t('noAppointments')}</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th></th>
                <th>{t('bookingNumber')}</th>
                <th>{t('guardian')}</th>
                <th>{t('student')}</th>
                <th>{t('appointmentTime')}</th>
                <th>{t('status')}</th>
              </tr>
            </thead>
            <tbody>
              {appts.map((a) => (
                <tr key={a.id}>
                  <td>
                    <input
                      type="checkbox"
                      disabled={a.status !== 'SCHEDULED'}
                      checked={selected.includes(a.id)}
                      onChange={() => toggle(a.id)}
                    />
                  </td>
                  <td>{a.booking_number}</td>
                  <td>{a.guardian_name}</td>
                  <td>{a.student_name}</td>
                  <td>{new Date(a.scheduled_at).toLocaleString()}</td>
                  <td>
                    <span className={`pill ${a.status.toLowerCase()}`}>{t(a.status.toLowerCase())}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="row" style={{ marginTop: 14 }}>
          <button className="btn" disabled={selected.length === 0 || loading} onClick={checkIn}>
            {t('checkInNow')} {selected.length > 0 && `(${selected.length})`}
          </button>
        </div>
      </div>

      <div className="card">
        <h2>{t('createWalkIn')}</h2>
        <div className="row">
          <input placeholder={t('walkInName')} value={walkInName} onChange={(e) => setWalkInName(e.target.value)} />
          <input placeholder={t('walkInPhone')} value={walkInPhone} onChange={(e) => setWalkInPhone(e.target.value)} />
          <button className="btn" disabled={!walkInName.trim() || loading} onClick={walkIn}>
            {t('createWalkIn')}
          </button>
        </div>
      </div>
    </div>
  )
}
