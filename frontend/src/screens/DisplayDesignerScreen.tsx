import { useEffect, useRef, useState } from 'react'
import { api, getToken } from '../api'
import { useI18n } from '../i18n'
import DisplayCanvas, { DisplayConfig, QueueData, WidgetConfig } from '../DisplayCanvas'

const PRESETS = ['default', 'light', 'dark', 'high_contrast']

function Num({ label, value, onChange, min, max }: { label: string; value: number; onChange: (v: number) => void; min?: number; max?: number }) {
  return (
    <label className="ds-field">
      <span>{label}</span>
      <input type="number" value={value} min={min} max={max} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  )
}

function Color({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="ds-field">
      <span>{label}</span>
      <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <input type="color" value={/^#[0-9a-fA-F]{6}$/.test(value) ? value : '#ffffff'} onChange={(e) => onChange(e.target.value)} style={{ width: 36, height: 30, padding: 0, border: '1px solid var(--border)' }} />
        <input type="text" value={value} onChange={(e) => onChange(e.target.value)} style={{ width: 90 }} />
      </span>
    </label>
  )
}

export default function DisplayDesignerScreen() {
  const { t } = useI18n()
  const [config, setConfig] = useState<DisplayConfig | null>(null)
  const [data, setData] = useState<QueueData | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [msg, setMsg] = useState('')
  const configRef = useRef<DisplayConfig | null>(null)
  const [history, setHistory] = useState<DisplayConfig[]>([])
  const [future, setFuture] = useState<DisplayConfig[]>([])

  useEffect(() => {
    api.get<DisplayConfig>('/api/display-config/draft').then((c) => { configRef.current = c; setConfig(c) }).catch((e) => setMsg(e.message))
    api.get<QueueData>('/api/public-display/state').then(setData).catch(() => {})
    const tmr = setInterval(() => api.get<QueueData>('/api/public-display/state').then(setData).catch(() => {}), 5000)
    return () => clearInterval(tmr)
  }, [])

  function commit(next: DisplayConfig) {
    if (configRef.current) setHistory((h) => [...h.slice(-60), configRef.current!])
    configRef.current = next
    setFuture([])
    setConfig(next)
  }

  const patchWidget = (id: string, patch: Partial<WidgetConfig>) => {
    if (!configRef.current) return
    commit({ ...configRef.current, widgets: { ...configRef.current.widgets, [id]: { ...configRef.current.widgets[id], ...patch } } })
  }
  const patchIdentity = (patch: Partial<DisplayConfig['identity']>) => {
    if (!configRef.current) return
    commit({ ...configRef.current, identity: { ...configRef.current.identity, ...patch } })
  }
  const patchTheme = (patch: Partial<DisplayConfig['theme']>) => {
    if (!configRef.current) return
    commit({ ...configRef.current, theme: { ...configRef.current.theme, ...patch } })
  }

  const saveDraft = async () => {
    if (!configRef.current) return
    setMsg('')
    try { await api.put('/api/display-config/draft', { config: configRef.current }); setMsg(t('success')) } catch (e: any) { setMsg(e.message) }
  }
  const publish = async () => {
    setMsg('')
    try { await api.post('/api/display-config/publish'); setMsg(t('success')) } catch (e: any) { setMsg(e.message) }
  }
  const applyPreset = async (p: string) => {
    setMsg('')
    try { const r: any = await api.post('/api/display-config/reset', { preset: p }); configRef.current = r.config; setConfig(r.config); setHistory([]); setFuture([]); setSelected(null) } catch (e: any) { setMsg(e.message) }
  }
  const undo = () => {
    setHistory((h) => {
      if (h.length === 0) return h
      const prev = h[h.length - 1]
      setFuture((f) => [...f, configRef.current!])
      configRef.current = prev
      setConfig(prev)
      return h.slice(0, -1)
    })
  }
  const redo = () => {
    setFuture((f) => {
      if (f.length === 0) return f
      const next = f[f.length - 1]
      setHistory((h) => [...h, configRef.current!])
      configRef.current = next
      setConfig(next)
      return f.slice(0, -1)
    })
  }
  const resetElement = () => {
    if (!selected || !configRef.current) return
    patchWidget(selected, { x: 0, y: 0, width: 400, height: 180, backgroundColor: '#ffffff', textColor: '#1a1d23', borderColor: '#e0e3e8', borderWidth: 1, borderRadius: 8, fontSize: 24, fontWeight: 700, textAlign: 'center', lineHeight: 1.2, visible: true, locked: false })
  }
  const uploadLogo = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    const token = getToken()
    try {
      const res = await fetch('/api/uploads', { method: 'POST', headers: token ? { Authorization: `Bearer ${token}` } : {}, body: fd })
      const j = await res.json()
      if (res.ok) patchIdentity({ logoUrl: j.url })
      else setMsg(j?.error?.message || 'Upload failed')
    } catch (err: any) {
      setMsg(err.message)
    }
  }

  const sel = selected && config ? config.widgets[selected] : null

  return (
    <div className="designer">
      <div className="designer-top">
        <h1>{t('displayDesigner')}</h1>
        <div className="row">
          <button className="btn ghost" onClick={undo} disabled={history.length === 0}>↺ Undo</button>
          <button className="btn ghost" onClick={redo} disabled={future.length === 0}>↻ Redo</button>
          <button className="btn ghost" onClick={() => applyPreset('default')}>{t('resetLayout')}</button>
          <button className="btn" onClick={saveDraft}>{t('saveDraft')}</button>
          <button className="btn" onClick={publish} style={{ background: 'var(--ok)' }}>{t('publish')}</button>
        </div>
        {msg && <div className="success-box" style={{ marginTop: 8 }}>{msg}</div>}
      </div>

      <div className="designer-body">
        {/* Settings panel */}
        <div className="designer-sidebar">
          <div className="card">
            <h2>{t('presets')}</h2>
            <div className="row">
              {PRESETS.map((p) => (
                <button key={p} className="btn ghost sm" onClick={() => applyPreset(p)}>{p}</button>
              ))}
            </div>
          </div>

          <div className="card">
            <h2>{t('identity')}</h2>
            <label className="ds-field"><span>{t('displayName')}</span><input type="text" value={config?.identity.name ?? ''} onChange={(e) => patchIdentity({ name: e.target.value })} placeholder={t('displayName')} /></label>
            <label className="ds-field"><span>{t('headerTitle')}</span><input type="text" value={config?.identity.headerTitle ?? ''} onChange={(e) => patchIdentity({ headerTitle: e.target.value })} /></label>
            <label className="ds-field"><span>{t('subtitle')}</span><input type="text" value={config?.identity.subtitle ?? ''} onChange={(e) => patchIdentity({ subtitle: e.target.value })} /></label>
            <label className="ds-field"><span>{t('logo')}</span><input type="file" accept="image/*" onChange={uploadLogo} /></label>
            {config?.identity.logoUrl && <img src={config.identity.logoUrl} alt="logo" style={{ height: 40, marginTop: 6 }} />}
            <div className="row" style={{ marginTop: 8 }}>
              <label className="ds-check"><input type="checkbox" checked={config?.identity.showLogo ?? true} onChange={(e) => patchIdentity({ showLogo: e.target.checked })} /> {t('showLogo')}</label>
              <label className="ds-check"><input type="checkbox" checked={config?.identity.showName ?? true} onChange={(e) => patchIdentity({ showName: e.target.checked })} /> {t('showName')}</label>
            </div>
          </div>

          <div className="card">
            <h2>{t('theme')}</h2>
            <Color label={t('background')} value={config?.theme.background ?? '#ffffff'} onChange={(v) => patchTheme({ background: v })} />
            <Color label={t('accent')} value={config?.theme.accent ?? '#2563eb'} onChange={(v) => patchTheme({ accent: v })} />
          </div>

          {sel && (
            <div className="card">
              <h2>{t('element')}: {selected}</h2>
              <div className="row" style={{ marginBottom: 8 }}>
                <button className="btn ghost sm" onClick={resetElement}>{t('resetElement')}</button>
              </div>
              <h3 style={{ fontSize: '0.85rem', margin: '8px 0' }}>{t('position')} / {t('size')}</h3>
              <div className="ds-grid">
                <Num label="X" value={sel.x} onChange={(v) => patchWidget(selected!, { x: v })} />
                <Num label="Y" value={sel.y} onChange={(v) => patchWidget(selected!, { y: v })} />
                <Num label="W" value={sel.width} min={40} onChange={(v) => patchWidget(selected!, { width: v })} />
                <Num label="H" value={sel.height} min={40} onChange={(v) => patchWidget(selected!, { height: v })} />
              </div>
              <h3 style={{ fontSize: '0.85rem', margin: '8px 0' }}>{t('colors')}</h3>
              <Color label={t('background')} value={sel.backgroundColor} onChange={(v) => patchWidget(selected!, { backgroundColor: v })} />
              <Color label={t('textColor')} value={sel.textColor} onChange={(v) => patchWidget(selected!, { textColor: v })} />
              <Color label={t('borderColor')} value={sel.borderColor} onChange={(v) => patchWidget(selected!, { borderColor: v })} />
              <div className="ds-grid">
                <Num label={t('borderWidth')} value={sel.borderWidth} min={0} onChange={(v) => patchWidget(selected!, { borderWidth: v })} />
                <Num label={t('borderRadius')} value={sel.borderRadius} min={0} onChange={(v) => patchWidget(selected!, { borderRadius: v })} />
              </div>
              <h3 style={{ fontSize: '0.85rem', margin: '8px 0' }}>{t('typography')}</h3>
              <div className="ds-grid">
                <Num label={t('fontSize')} value={sel.fontSize} min={8} onChange={(v) => patchWidget(selected!, { fontSize: v })} />
                <Num label={t('fontWeight')} value={sel.fontWeight} min={100} max={900} onChange={(v) => patchWidget(selected!, { fontWeight: v })} />
              </div>
              <label className="ds-field"><span>{t('textAlign')}</span>
                <select value={sel.textAlign} onChange={(e) => patchWidget(selected!, { textAlign: e.target.value })}>
                  <option value="left">Left</option><option value="center">Center</option><option value="right">Right</option>
                </select>
              </label>
              <label className="ds-check" style={{ marginTop: 8 }}>
                <input type="checkbox" checked={sel.visible} onChange={(e) => patchWidget(selected!, { visible: e.target.checked })} /> {t('visible')}
              </label>
              <label className="ds-check" style={{ marginTop: 4 }}>
                <input type="checkbox" checked={sel.locked} onChange={(e) => patchWidget(selected!, { locked: e.target.checked })} /> {t('lockPosition')}
              </label>
            </div>
          )}

          {!sel && <div className="card muted">{t('selectElementHint')}</div>}
        </div>

        {/* Live canvas */}
        <div className="designer-canvas">
          {config && (
            <DisplayCanvas
              config={config}
              data={data}
              editable
              selectedId={selected}
              onSelect={setSelected}
              onWidgetChange={patchWidget}
            />
          )}
        </div>
      </div>
    </div>
  )
}
