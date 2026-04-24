/**
 * On macOS with hiddenInset title bar the window controls overlap the content,
 * so we reserve 32px at the top as a drag region. On Windows the native title
 * bar handles all of this, so we render nothing.
 */
export default function TitleBarSpacer() {
  const isMac = window.electronAPI?.platform() === 'darwin'
  if (!isMac) return null
  return <div className="drag-region h-8 shrink-0" />
}
