import { useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'

export default function SettingsScreen() {
  const { t, locale, setLocale } = useI18n()
  const { user } = useAuth()
  const [msg, setMsg] = useState('')

  const change = async (l: 'en' | 'ar') => {
    setMsg('')
    try {
      await api.put('/api/settings/language', { scope: 'user', locale: l })
      setLocale(l)
      setMsg(t('success'))
    } catch (e: any) {
      setMsg(e.message)
    }
  }

  const changePublic = async (l: 'en' | 'ar') => {
    setMsg('')
    try {
      await api.put('/api/settings/language', { scope: 'calling_screen', locale: l })
      setMsg(t('success'))
    } catch (e: any) {
      setMsg(e.message)
    }
  }

  return (
    <div>
      <h1>{t('settings')}</h1>
      <div className="card">
        <h2>{t('language')}</h2>
        {msg && <div className="success-box">{msg}</div>}
        <div className="row">
          <button className={`btn ${locale === 'en' ? '' : 'ghost'}`} onClick={() => change('en')}>
            {t('english')}
          </button>
          <button className={`btn ${locale === 'ar' ? '' : 'ghost'}`} onClick={() => change('ar')}>
            {t('arabic')}
          </button>
        </div>
        {user?.role === 'ADMIN' && (
          <>
            <h2 style={{ marginTop: 20 }}>{t('callingScreen')} — {t('language')}</h2>
            <div className="row">
              <button className="btn ghost" onClick={() => changePublic('en')}>
                {t('english')}
              </button>
              <button className="btn ghost" onClick={() => changePublic('ar')}>
                {t('arabic')}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
