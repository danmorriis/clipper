/**
 * Reserves space at the top of the window for the title bar area.
 * - macOS: 32px drag region for hiddenInset window controls
 * - Windows: 32px drag region for custom window controls (frameless mode)
 * - Other: nothing
 */
export default function TitleBarSpacer() {
  const platform = window.electronAPI?.platform()
  if (platform !== 'darwin' && platform !== 'win32') return null
  return <div className="drag-region h-8 shrink-0" />
}
