import { useEffect, useState } from 'react'

export function useDarkMode() {
  const [dark, setDark] = useState(() => localStorage.getItem('clb-dark') === '1')

  useEffect(() => {
    const root = document.getElementById('root')
    if (!root) return
    if (dark) root.classList.add('dark')
    else root.classList.remove('dark')
    localStorage.setItem('clb-dark', dark ? '1' : '0')
  }, [dark])

  return { dark, toggle: () => setDark((d) => !d) }
}
