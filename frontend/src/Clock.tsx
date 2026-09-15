import { useEffect, useState } from 'react'

export default function Clock({ className, full }: { className?: string; full?: boolean }) {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])
  const date = full
    ? now.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })
    : now.toLocaleDateString()
  const time = now.toLocaleTimeString()
  return (
    <span className={className}>
      {date} · {time}
    </span>
  )
}
