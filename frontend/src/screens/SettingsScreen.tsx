import { useEffect, useState } from 'react'
import { api } from '../api'
import { useI18n } from '../i18n'
import { useAuth } from '../auth'
import { useOrganization } from '../org'

export default function SettingsScreen() {
  const { t, locale, setLocale } = useI18n()
  const { user } = useAuth()
  const { org, refresh } = useOrganization()
  const [msg, setMsg] = useState('')
  const [name, setName] = useState('')
  const [tagline, setTagline] = useState('')

  useEffect(() => {
    setName(org.name)
    setTagline(org.tagline)
  }, [org])

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

  const changeApp = async (l: 'en' | 'ar') => {
    setMsg('')
    try {
      await api.put('/api/settings/language', { scope: 'app', locale: l })
      setMsg(t('success'))
    } catch (e: any) {
      setMsg(e.message)
    }
  }

  const saveOrg = async () => {
    setMsg('')
    try {
      await api.put('/api/settings/organization', { name, tagline })
      await refresh()
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
            <h2 style={{ marginTop: 20 }}>{t('appLanguage')}</h2>
            <div className="row">
              <button className="btn ghost" onClick={() => changeApp('en')}>
                {t('english')}
              </button>
              <button className="btn ghost" onClick={() => changeApp('ar')}>
                {t('arabic')}
              </button>
            </div>
          </>
        )}
        {user?.role === 'ADMIN' && (
          <>
            <h2 style={{ marginTop: 20 }}>{t('organization')}</h2>
            <div className="row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
              <input placeholder={t('clientName')} value={name} onChange={(e) => setName(e.target.value)} />
              <input placeholder={t('tagline')} value={tagline} onChange={(e) => setTagline(e.target.value)} />
              <button className="btn" onClick={saveOrg}>
                {t('save')}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
