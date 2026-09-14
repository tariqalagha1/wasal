// Minimal WebSocket client: reconnects, notifies subscribers, exposes online state.
// WebSocket messages are notifications only; screens refetch authoritative REST state.

type Listener = (event: any) => void

class WsClient {
  private ws: WebSocket | null = null
  private listeners = new Set<Listener>()
  private onlineListeners = new Set<(online: boolean) => void>()
  online = true

  connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${location.host}/ws`
    this.ws = new WebSocket(url)
    this.ws.onopen = () => {
      this.setOnline(true)
    }
    this.ws.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data)
        this.listeners.forEach((l) => l(event))
      } catch {
        /* ignore */
      }
    }
    this.ws.onclose = () => {
      this.setOnline(false)
      setTimeout(() => this.connect(), 1500)
    }
    this.ws.onerror = () => {
      this.setOnline(false)
    }
    // Also track browser network state for prompt offline detection.
    window.addEventListener('online', () => this.setOnline(true))
    window.addEventListener('offline', () => this.setOnline(false))
    this.online = navigator.onLine
  }

  private setOnline(v: boolean) {
    this.online = v
    this.onlineListeners.forEach((l) => l(v))
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  onOnline(listener: (online: boolean) => void): () => void {
    this.onlineListeners.add(listener)
    return () => this.onlineListeners.delete(listener)
  }
}

export const wsClient = new WsClient()
