import { useCallback, useRef } from 'react'
import { authHeader } from '../api/client'
import type { ProgressEvent } from '../types'

type SSECallback = (event: ProgressEvent) => void

export function useSSE() {
  const abortRef = useRef<AbortController | null>(null)

  const connect = useCallback((
    url: string,
    onEvent: SSECallback,
    onClose?: () => void,
    isTerminal?: (event: ProgressEvent) => boolean,
  ) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    ;(async () => {
      try {
        const res = await fetch(url, {
          headers: { ...authHeader(), Accept: 'text/event-stream' },
          signal: controller.signal,
        })

        if (!res.ok || !res.body) return

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buf += decoder.decode(value, { stream: true })
          const lines = buf.split('\n')
          buf = lines.pop() ?? ''

          for (const line of lines) {
            if (!line.startsWith('data:')) continue
            const raw = line.slice(5).trim()
            if (!raw) continue
            try {
              const data: ProgressEvent = JSON.parse(raw)
              onEvent(data)
              const terminal = isTerminal
                ? isTerminal(data)
                : (!!data.done || !!data.error || !!data.cancelled)
              if (terminal) {
                controller.abort()
                onClose?.()
                return
              }
            } catch {
              // ignore parse errors
            }
          }
        }
      } catch (err: any) {
        if (err?.name !== 'AbortError') onClose?.()
      }
    })()
  }, [])

  const close = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  return { connect, close }
}
