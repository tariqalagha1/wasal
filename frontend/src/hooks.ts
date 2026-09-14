import { useEffect, useState } from 'react'
import { wsClient } from './ws'

export function useOnline(): boolean {
  const [online, setOnline] = useState<boolean>(wsClient.online)
  useEffect(() => {
    wsClient.connect()
    return wsClient.onOnline(setOnline)
  }, [])
  return online
}

// Polls `fetchFn` every `intervalMs`, plus immediately on any matching WebSocket event.
export function useLive<T>(fetchFn: () => Promise<T>, intervalMs: number, eventTypes?: string[]): T | null {
  const [data, setData] = useState<T | null>(null)

  useEffect(() => {
    let mounted = true
    const load = () => fetchFn().then((d) => mounted && setData(d)).catch(() => {})
    load()
    const timer = setInterval(load, intervalMs)
    const unsub = eventTypes
      ? wsClient.subscribe((ev) => {
          if (!eventTypes || eventTypes.includes(ev.type)) load()
        })
      : () => {}
    return () => {
      mounted = false
      clearInterval(timer)
      unsub()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, JSON.stringify(eventTypes ?? [])])

  return data
}
