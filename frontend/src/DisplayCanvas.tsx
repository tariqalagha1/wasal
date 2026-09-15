import { useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'
import { useI18n } from './i18n'
import { useOrganization } from './org'
import Clock from './Clock'

export interface WidgetConfig {
  visible: boolean
  x: number
  y: number
  width: number
  height: number
  backgroundColor: string
  textColor: string
  borderColor: string
  borderWidth: number
  borderRadius: number
  fontSize: number
  fontWeight: number
  textAlign: string
  lineHeight: number
  locked: boolean
}

export interface IdentityConfig {
  name: string
  headerTitle: string
  subtitle: string
  logoUrl: string
  showLogo: boolean
  showName: boolean
}

export interface DisplayConfig {
  version: number
  resolution: { width: number; height: number }
  theme: { background: string; primary: string; accent: string; text: string }
  identity: IdentityConfig
  widgets: Record<string, WidgetConfig>
}

export interface QueueData {
  now_serving: { ticket_number: number; counter_name: string } | null
  counters: { code: string; display_name: string; current_ticket: number | null }[]
  waiting: { ticket_number: number; position: number }[]
  missed: { ticket_number: number; counter_name: string; missed_at: string | null }[]
}

export const WIDGET_ORDER = ['header', 'clock', 'nowTitle', 'nowTicket', 'nowCounter', 'counters', 'waiting', 'missed']

function widgetStyle(cfg: WidgetConfig): CSSProperties {
  return {
    position: 'absolute',
    left: cfg.x,
    top: cfg.y,
    width: cfg.width,
    height: cfg.height,
    background: cfg.backgroundColor,
    color: cfg.textColor,
    border: cfg.borderWidth > 0 ? `${cfg.borderWidth}px solid ${cfg.borderColor}` : 'none',
    borderRadius: cfg.borderRadius,
    fontSize: cfg.fontSize,
    fontWeight: cfg.fontWeight,
    textAlign: cfg.textAlign as any,
    lineHeight: cfg.lineHeight,
    overflow: 'hidden',
    boxSizing: 'border-box',
  }
}

function WidgetContent({ id, cfg, data, org, t }: { id: string; cfg: DisplayConfig; data: QueueData | null; org: { name: string; tagline: string }; t: (k: string) => string }) {
  const ident = cfg.identity
  switch (id) {
    case 'header': {
      const name = ident.headerTitle || ident.name || org.name || t('appName')
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '0 12px', height: '100%' }}>
          {ident.showLogo && ident.logoUrl && (
            <img src={ident.logoUrl} alt="logo" style={{ height: '80%', maxHeight: 80, objectFit: 'contain' }} />
          )}
          {ident.showName && (
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: '1em', fontWeight: 800 }}>{name}</div>
              {ident.subtitle && <div style={{ fontSize: '0.5em', fontWeight: 500, opacity: 0.75 }}>{ident.subtitle}</div>}
            </div>
          )}
        </div>
      )
    }
    case 'clock':
      return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', height: '100%', padding: '0 12px' }}>
          <Clock full />
        </div>
      )
    case 'nowTitle':
      return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>{t('nowServing')}</div>
    case 'nowTicket':
      return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
          {data?.now_serving ? data.now_serving.ticket_number : '—'}
        </div>
      )
    case 'nowCounter':
      return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
          {data?.now_serving ? `${t('proceedTo')} ${data.now_serving.counter_name}` : ''}
        </div>
      )
    case 'counters':
      return (
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <div style={{ fontSize: '0.5em', fontWeight: 700, opacity: 0.6, padding: '10px 0 6px' }}>{t('counters')}</div>
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, padding: '0 10px 10px' }}>
            {(data?.counters ?? []).map((c) => (
              <div key={c.code} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 10px', borderRadius: 6, background: 'rgba(127,127,127,0.12)' }}>
                <span>{c.code}</span>
                <span style={{ fontWeight: 900 }}>{c.current_ticket ?? '—'}</span>
              </div>
            ))}
          </div>
        </div>
      )
    case 'waiting':
    case 'missed': {
      const list = id === 'waiting' ? (data?.waiting ?? []) : (data?.missed ?? [])
      const title = id === 'waiting' ? t('waitingBookings') : t('missedBookings')
      return (
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <div style={{ fontSize: '0.5em', fontWeight: 700, opacity: 0.6, padding: '10px 0 6px' }}>{title}</div>
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexWrap: 'wrap', gap: 8, padding: '0 10px 10px', alignContent: 'flex-start' }}>
            {list.length === 0 ? (
              <div style={{ opacity: 0.5, fontSize: '0.5em' }}>{t('noMissed')}</div>
            ) : (
              list.map((m: any, i: number) => (
                <span key={i} style={{ padding: '4px 12px', borderRadius: 6, background: id === 'waiting' ? 'rgba(37,99,235,0.15)' : 'rgba(220,38,38,0.15)', fontSize: '0.6em' }}>
                  {m.ticket_number}
                </span>
              ))
            )}
          </div>
        </div>
      )
    }
    default:
      return null
  }
}

export default function DisplayCanvas({
  config,
  data,
  editable = false,
  selectedId,
  onSelect,
  onWidgetChange,
}: {
  config: DisplayConfig
  data: QueueData | null
  editable?: boolean
  selectedId?: string | null
  onSelect?: (id: string | null) => void
  onWidgetChange?: (id: string, patch: Partial<WidgetConfig>) => void
}) {
  const { t } = useI18n()
  const { org } = useOrganization()
  const viewportRef = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(0.5)
  const RES_W = config.resolution?.width || 1920
  const RES_H = config.resolution?.height || 1080

  useEffect(() => {
    const el = viewportRef.current
    if (!el) return
    const update = () => {
      const r = el.getBoundingClientRect()
      const s = Math.min(r.width / RES_W, r.height / RES_H)
      setScale(s > 0 ? s : 0.5)
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [RES_W, RES_H])

  const dragRef = useRef<{ id: string; mode: 'move' | 'resize'; startX: number; startY: number; origX: number; origY: number; origW: number; origH: number } | null>(null)

  const onPointerDown = (e: ReactPointerEvent, id: string, mode: 'move' | 'resize') => {
    if (!editable || !onWidgetChange) return
    e.stopPropagation()
    e.preventDefault()
    const cfg = config.widgets[id]
    dragRef.current = { id, mode, startX: e.clientX, startY: e.clientY, origX: cfg.x, origY: cfg.y, origW: cfg.width, origH: cfg.height }
    onSelect?.(id)
    const onMove = (ev: PointerEvent) => {
      const d = dragRef.current
      if (!d) return
      const dx = (ev.clientX - d.startX) / scale
      const dy = (ev.clientY - d.startY) / scale
      if (d.mode === 'move') {
        onWidgetChange(d.id, { x: Math.round(d.origX + dx), y: Math.round(d.origY + dy) })
      } else {
        onWidgetChange(d.id, { width: Math.max(40, Math.round(d.origW + dx)), height: Math.max(40, Math.round(d.origH + dy)) })
      }
    }
    const onUp = () => {
      dragRef.current = null
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  return (
    <div ref={viewportRef} className="dc-viewport" style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#111' }}>
      <div style={{ width: RES_W * scale, height: RES_H * scale, position: 'relative', flexShrink: 0 }}>
        <div style={{ position: 'absolute', left: 0, top: 0, width: RES_W, height: RES_H, transform: `scale(${scale})`, transformOrigin: 'top left', background: config.theme?.background || '#f5f6f8' }}>
          {WIDGET_ORDER.map((id) => {
            const w = config.widgets[id]
            if (!w || !w.visible) return null
            const isSel = editable && selectedId === id
            return (
              <div
                key={id}
                data-widget={id}
                style={{ ...widgetStyle(w), cursor: editable && !w.locked ? 'move' : 'default', boxShadow: isSel ? '0 0 0 2px #2563eb' : 'none', zIndex: isSel ? 10 : 1 }}
                onPointerDown={(e) => editable && onSelect?.(id)}
                onClick={(e) => { if (editable) { e.stopPropagation(); onSelect?.(id) } }}
              >
                <div
                  style={{ width: '100%', height: '100%', cursor: editable && !w.locked ? 'move' : 'default' }}
                  onPointerDown={(e) => onPointerDown(e, id, 'move')}
                >
                  <WidgetContent id={id} cfg={config} data={data} org={org} t={t} />
                </div>
                {isSel && !w.locked && (
                  <div
                    style={{ position: 'absolute', right: -8, bottom: -8, width: 16, height: 16, background: '#2563eb', borderRadius: '50%', cursor: 'nwse-resize' }}
                    onPointerDown={(e) => onPointerDown(e, id, 'resize')}
                  />
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
