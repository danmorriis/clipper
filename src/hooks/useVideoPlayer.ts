import { useCallback, useEffect, useRef, useState } from 'react'

interface UseVideoPlayerOptions {
  clipStart: number   // seconds
  clipEnd: number     // seconds
}

export function useVideoPlayer({ clipStart, clipEnd }: UseVideoPlayerOptions) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(clipStart)
  const clipStartRef = useRef(clipStart)
  const clipEndRef = useRef(clipEnd)

  // Keep refs in sync so the timeupdate handler has current values
  useEffect(() => { clipStartRef.current = clipStart }, [clipStart])
  useEffect(() => { clipEndRef.current = clipEnd }, [clipEnd])

  // Enforce clip window: pause at clipEnd
  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const onTimeUpdate = () => {
      setCurrentTime(video.currentTime)
      if (video.currentTime >= clipEndRef.current) {
        video.pause()
        setPlaying(false)
      }
    }

    const onPlay = () => setPlaying(true)
    const onPause = () => setPlaying(false)

    video.addEventListener('timeupdate', onTimeUpdate)
    video.addEventListener('play', onPlay)
    video.addEventListener('pause', onPause)

    return () => {
      video.removeEventListener('timeupdate', onTimeUpdate)
      video.removeEventListener('play', onPlay)
      video.removeEventListener('pause', onPause)
    }
  }, [])

  const seekTo = useCallback((t: number) => {
    const video = videoRef.current
    if (!video) return
    video.currentTime = t
    setCurrentTime(t)
  }, [])

  const play = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    // If at or past clip end, restart from clip start
    if (video.currentTime >= clipEndRef.current) {
      video.currentTime = clipStartRef.current
    }
    video.play()
  }, [])

  const pause = useCallback(() => {
    videoRef.current?.pause()
  }, [])

  const toggle = useCallback(() => {
    if (videoRef.current?.paused) {
      play()
    } else {
      pause()
    }
  }, [play, pause])

  const stop = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    video.pause()
    video.currentTime = clipStartRef.current
    setCurrentTime(clipStartRef.current)
  }, [])

  // Seek into clip when clipStart changes (e.g. edit mode)
  const loadClip = useCallback((start: number, end: number) => {
    clipStartRef.current = start
    clipEndRef.current = end
    seekTo(start)
  }, [seekTo])

  return {
    videoRef,
    playing,
    currentTime,
    seekTo,
    play,
    pause,
    toggle,
    stop,
    loadClip,
  }
}
