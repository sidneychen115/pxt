import { useEffect, useRef, useCallback } from 'react'

type MessageHandler = (channel: string, data: unknown) => void

export function useWebSocket(onMessage: MessageHandler) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onMessageRef = useRef(onMessage)
  const isMounted = useRef(true)

  useEffect(() => {
    onMessageRef.current = onMessage
  })

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws`)
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const { channel, data } = JSON.parse(event.data)
        onMessageRef.current(channel, data)
      } catch {}
    }

    ws.onclose = () => {
      if (isMounted.current) {
        reconnectTimer.current = setTimeout(connect, 3000)
      }
    }
  }, [])  // no onMessage dependency

  useEffect(() => {
    isMounted.current = true
    connect()
    return () => {
      isMounted.current = false
      wsRef.current?.close()
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
    }
  }, [connect])
}
