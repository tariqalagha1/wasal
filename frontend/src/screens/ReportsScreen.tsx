import { useEffect, useState } from 'react'
import { api, getToken } from '../api'
import { useI18n } from '../i18n'

interface Row {
  ticket_number: number
  visit_type: string
  guardian_name: string
  student_names: string | null
  booking_numbers: string | null
  ticket_status: string
  arrival_at: string | null
  queue_entered_at: string | null
  called_at: string | null
  completed_at: string | null
  waiting_seconds: number | null
  service_seconds: number | null
  cashier: string | null
}

export default function ReportsScreen() {
  const { t } = useI18n()
  const [rows, setRows] = useState<Row[]>([])
  const [visitType, setVisitType] = useState('')

  const load = async () => {
    const q = visitType ? `?visit_type=${encodeURIComponent(visitType)}` : ''
    const res = await api.get<{ rows: Row[] }>(`/api/reports/appointments${q}`)
    setRows(res.rows)
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const exportCsv = () => {
    const token = getToken()
    fetch(`/api/reports/appointments.csv`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'appointments.csv'
        a.click()
        URL.revokeObjectURL(url)
      })
  }

  const fmtSec = (s: number | null) => (s == null ? '—' : `${Math.floor(s / 60)}m ${s % 60}s`)

  return (
    <div>
      <h1>{t('reports')}</h1>
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <select value={visitType} onChange={(e) => setVisitType(e.target.value)}>
            <option value="">All</option>
            <option value="SCHEDULED">SCHEDULED</option>
            <option value="EARLY">EARLY</option>
            <option value="LATE">LATE</option>
            <option value="WALK_IN">WALK_IN</option>
          </select>
          <button className="btn ghost" onClick={load}>
            {t('search')}
          </button>
          <button className="btn" onClick={exportCsv}>
            {t('exportCsv')}
          </button>
        </div>
        <table>
          <thead>
            <tr>
              <th>{t('ticketNumber')}</th>
              <th>{t('visitType')}</th>
              <th>{t('guardian')}</th>
              <th>{t('student')}</th>
              <th>{t('bookingNumber')}</th>
              <th>{t('ticket')} {t('status')}</th>
              <th>{t('window')}</th>
              <th>{t('waitingDuration')}</th>
              <th>{t('serviceDuration')}</th>
              <th>{t('completedAt')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td style={{ fontWeight: 700 }}>{r.ticket_number}</td>
                <td>
                  <span className={`pill ${r.visit_type.toLowerCase()}`}>{t(r.visit_type.toLowerCase())}</span>
                </td>
                <td>{r.guardian_name}</td>
                <td>{r.student_names || '—'}</td>
                <td>{r.booking_numbers || '—'}</td>
                <td>
                  <span className={`pill ${r.ticket_status.toLowerCase()}`}>{t(r.ticket_status.toLowerCase())}</span>
                </td>
                <td>{r.cashier || '—'}</td>
                <td>{fmtSec(r.waiting_seconds)}</td>
                <td>{fmtSec(r.service_seconds)}</td>
                <td>{r.completed_at ? new Date(r.completed_at).toLocaleString() : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
